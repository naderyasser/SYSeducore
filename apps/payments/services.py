from datetime import date
from decimal import Decimal

from apps.teachers.models import Group

from .models import Payment


def _fee_for(enrollment, group):
    """
    Expected monthly fee for an enrollment — the same rule as
    ``Student.get_monthly_fee_for_group`` but without a query per student.
    """
    if enrollment is None:
        return Decimal('0')
    if enrollment.financial_status == 'exempt':
        return Decimal('0')
    if enrollment.financial_status == 'symbolic':
        return enrollment.custom_fee or Decimal('0')
    return group.standard_fee or Decimal('0')


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
