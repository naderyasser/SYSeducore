from datetime import date
from decimal import Decimal

from apps.teachers.models import Group

from .models import (
    Payment, TeacherSettlement, TeacherSettlementLine, SettlementLockedError, to_money,
)
from .pricing import base_fee as _fee_for, base_fee


class SettlementService:

    @staticmethod
    def calculate_teacher_settlement(teacher_id, year, month):
        """
        حساب مستحقات المدرس لشهر معين

        Includes groups that are inactive or soft-deleted: a group closed
        half-way through the month still earned money that month, and
        filtering it out made that revenue — and the teacher's share of it —
        disappear from the settlement.
        """
        groups = list(
            Group.all_objects.filter(teacher_id=teacher_id).order_by('group_id')
        )

        total_revenue = Decimal('0')
        total_center_share = Decimal('0')
        breakdown = []

        for group in groups:
            group_data = SettlementService.calculate_group_revenue(
                group.group_id, year, month, group=group,
            )

            group_revenue = Decimal(str(group_data['revenue']))
            group_center_percentage = group.center_percentage
            group_center_share = group_revenue * (group_center_percentage / Decimal('100'))
            group_teacher_share = group_revenue - group_center_share

            total_revenue += group_revenue
            total_center_share += group_center_share

            breakdown.append({
                'group_name': group.group_name,
                'group_active': group.is_active and group.deleted_at is None,
                'students': group_data['students'],
                'revenue': float(group_revenue),
                'center_percentage': float(group_center_percentage),
                'center_share': float(group_center_share),
                'teacher_share': float(group_teacher_share)
            })

        teacher_share = total_revenue - total_center_share

        # Calculate average center percentage for display
        avg_center_percentage = Decimal('0')
        if groups:
            total_percentage = sum(g.center_percentage for g in groups)
            avg_center_percentage = total_percentage / len(groups)

        return {
            'success': True,
            'data': {
                'teacher_id': teacher_id,
                'year': year,
                'month': month,
                'total_revenue': round(float(total_revenue), 2),
                'center_share': round(float(total_center_share), 2),
                'teacher_share': round(float(teacher_share), 2),
                'center_percentage': float(avg_center_percentage),
                'breakdown': breakdown
            }
        }

    @staticmethod
    def calculate_group_revenue(group_id, year, month, group=None):
        """
        حساب إيرادات مجموعة معينة
        الآن يدعم الطلاب المسجلين في مجموعات متعددة

        Revenue is the sum of ``amount_paid`` — money actually collected,
        not money owed.

        Enrollments and fees are resolved with two queries for the whole
        group instead of two queries *per payment row*.
        """
        from apps.students.models import StudentGroupEnrollment

        start_date = date(year, month, 1)

        # آخر يوم في الشهر
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)

        if group is None:
            group = Group.all_objects.filter(pk=group_id).first()
            if group is None:
                return {'revenue': 0.0, 'students': []}

        payments = Payment.objects.filter(
            group_id=group_id,
            month__gte=start_date,
            month__lt=end_date,
        ).select_related('student')

        enrollments = {
            enr.student_id: enr
            for enr in StudentGroupEnrollment.objects.filter(group_id=group_id)
        }

        revenue = Decimal('0')
        students = []

        for payment in payments:
            enrollment = enrollments.get(payment.student_id)
            financial_status_display = (
                enrollment.get_financial_status_display()
                if enrollment is not None else 'غير محدد'
            )
            expected_fee = _fee_for(enrollment, group)
            amount_paid = payment.amount_paid

            revenue += amount_paid

            students.append({
                'name': payment.student.full_name,
                'financial_status': financial_status_display,
                'expected_fee': float(expected_fee),
                'amount_paid': float(amount_paid),
                'payment_status': payment.get_status_display(),
                'sessions_attended': payment.sessions_attended,
                'is_exempt': payment.is_exempt,
            })

        return {
            'revenue': float(revenue),
            'students': students
        }

    # ------------------------------------------------------------------
    #  Persisted, editable, approvable settlement sheet
    # ------------------------------------------------------------------

    @staticmethod
    def _prorate_by_sessions(fee_full, sessions_consumed, sessions_entitled):
        """
        A student who consumed 2 of their 4 entitled sessions is billed (for
        settlement purposes) at half the full-cycle fee — never at the full
        amount, regardless of what they were actually invoiced. Mirrors the
        client's explicit rule: "الطالب الذي حضر حصصاً أقل لا يُحسب كمن حضر
        الشهر كاملاً".
        """
        fee_full = to_money(fee_full)
        if sessions_entitled <= 0:
            return fee_full
        n = min(sessions_consumed, sessions_entitled)
        return to_money(fee_full * Decimal(n) / Decimal(sessions_entitled))

    @staticmethod
    def _session_dates_for(student_id, cycle_id):
        if not cycle_id:
            return []
        from apps.attendance.models import Attendance
        dates = (
            Attendance.objects.filter(
                student_id=student_id, session__cycle_id=cycle_id, session__is_cancelled=False,
            )
            .order_by('session__session_date')
            .values_list('session__session_date', flat=True)
        )
        return [d.isoformat() for d in dates]

    @staticmethod
    def build_or_refresh(teacher, period_start, period_end, user=None):
        """
        Create (or refresh, if still ``draft``) the persisted settlement
        sheet for ``teacher`` over ``[period_start, period_end]``.

        Refreshing rewrites only the SNAPSHOT columns on each line — every
        manual override (``is_excluded``, ``is_free``, ``amount_override``,
        ``percentage_override``) survives untouched, which is the entire
        point of separating the two: an operator's edit can never be wiped
        out by "إعادة الحساب".

        Raises :class:`~apps.payments.models.SettlementLockedError` if the
        sheet is already approved — reopen it first.
        """
        from apps.students.models import StudentGroupEnrollment

        settlement, created = TeacherSettlement.objects.get_or_create(
            teacher=teacher, period_start=period_start, period_end=period_end,
            defaults={'created_by': user},
        )
        if settlement.status == TeacherSettlement.STATUS_APPROVED:
            raise SettlementLockedError('الكشف معتمد — يجب إعادة فتحه أولاً قبل إعادة الحساب')

        groups = list(Group.all_objects.filter(teacher=teacher))
        group_ids = [g.group_id for g in groups]
        groups_by_id = {g.group_id: g for g in groups}

        # ``Payment.month`` is a *bucket* — always the first of the month — not
        # the day the money moved. Comparing it against ``period_start``
        # directly therefore drops a whole month whenever the period does not
        # begin on the 1st: a sheet for 2 Aug — 1 Sep excluded every August
        # payment and came out at 0.00 next to an identical-looking sheet for
        # 1 Aug — 31 Aug worth 5,653 EGP. One day of difference, the teacher's
        # entire month of earnings. The bucket is included when it *overlaps*
        # the period, which is what the desk means by "this period".
        period_first_bucket = period_start.replace(day=1)
        payments = (
            Payment.objects.filter(
                group_id__in=group_ids,
                month__gte=period_first_bucket, month__lte=period_end,
            )
            .select_related('student', 'cycle')
            .order_by('month', 'payment_id')
        )

        enrollments = {
            (enr.group_id, enr.student_id): enr
            for enr in StudentGroupEnrollment.objects.filter(group_id__in=group_ids)
        }

        existing_lines = {(l.group_id, l.student_id): l for l in settlement.lines.all()}
        # One line per (group, student) — the table is unique on that — but a
        # period can legitimately span several cycles, so a student may have
        # several payments in it. Iterating payments directly built a second
        # line for the same pair and the insert died on the unique constraint:
        # a settlement covering more than one cycle failed with a 500 rather
        # than a sheet. Payments are grouped first and their cycles summed.
        payments_by_key = {}
        for payment in payments:
            payments_by_key.setdefault(
                (payment.group_id, payment.student_id), []
            ).append(payment)

        seen_keys = set()

        for key, key_payments in payments_by_key.items():
            seen_keys.add(key)
            group_id, student_id = key
            group = groups_by_id.get(group_id)
            enrollment = enrollments.get(key)

            line = existing_lines.get(key)
            if line is None:
                line = TeacherSettlementLine(
                    settlement=settlement, group_id=group_id, student_id=student_id,
                )

            # The most recent payment represents the line (its cycle is the one
            # shown); the money and the sessions are the sum over the period.
            latest = key_payments[-1]
            per_cycle_fee = (
                base_fee(enrollment, group) if (enrollment and group)
                else to_money(latest.amount_due)
            )

            sessions_entitled = sum(p.sessions_total for p in key_payments)
            sessions_consumed = sum(p.sessions_attended for p in key_payments)
            collected = sum((p.amount_paid for p in key_payments), to_money(0))
            # Pro-rated per cycle and then added up: pro-rating the summed
            # totals against a summed entitlement would silently let a fully
            # attended cycle subsidise a barely attended one.
            computed = sum(
                (
                    SettlementService._prorate_by_sessions(
                        per_cycle_fee, p.sessions_attended, p.sessions_total,
                    )
                    for p in key_payments
                ),
                to_money(0),
            )

            session_dates = []
            for p in key_payments:
                session_dates.extend(
                    SettlementService._session_dates_for(p.student_id, p.cycle_id)
                )

            line.cycle = latest.cycle
            line.payment = latest
            line.sessions_consumed = sessions_consumed
            line.sessions_entitled = sessions_entitled
            line.session_dates = session_dates
            # "Full price" for the line means the full price of everything the
            # period covers, so it stays comparable with the summed amounts
            # beside it.
            line.fee_full = to_money(per_cycle_fee * len(key_payments))
            line.computed_amount = computed
            line.collected_amount = collected
            line.financial_status = enrollment.financial_status if enrollment else ''
            line.group_center_percentage = group.center_percentage if group else settlement.default_center_percentage
            line.apply()
            line.save(force_locked=True)

        # A line whose payment disappeared from this period (enrollment
        # removed, payment deleted) is EXCLUDED, never deleted — deleting it
        # would erase the audit trail of what the teacher was once credited.
        for key, line in existing_lines.items():
            if key not in seen_keys and not line.is_excluded:
                line.is_excluded = True
                if not line.override_reason:
                    line.override_reason = 'لم يعد له دفعة في هذه الفترة'
                line.apply()
                line.save(force_locked=True)

        if created or not groups:
            avg_pct = (
                sum(g.center_percentage for g in groups) / len(groups)
                if groups else Decimal('30.00')
            )
            settlement.default_center_percentage = avg_pct
            settlement.save(update_fields=['default_center_percentage'])

        settlement.recalculate_totals()
        return settlement
