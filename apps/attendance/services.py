import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Attendance, Session
from apps.students.models import Student, StudentGroupEnrollment
from apps.payments.models import Payment
from apps.teachers.models import WEEK_DAYS_AR

logger = logging.getLogger('attendance')

# Arabic day names for user-facing messages.
# ``apps.teachers`` owns the canonical map; aliased here because this module's
# name for it is part of its own (widely imported) surface.
DAY_NAMES_AR = WEEK_DAYS_AR

# Maps error_type → UI severity for the frontend card color
SEVERITY_MAP = {
    'not_found': 'error',
    'invalid_code': 'error',
    'payment_required': 'warning',
    'sessions_exhausted': 'warning',
    'too_early': 'info',
    'too_late': 'warning',
    'no_session_today': 'info',
    'no_groups': 'warning',
    'wrong_schedule': 'info',
    'skipped': 'warning',
    'no_session': 'info',
    'no_cycle': 'info',
}


def get_local_tz():
    """The centre's timezone as a stdlib :class:`~zoneinfo.ZoneInfo`."""
    return ZoneInfo(settings.TIME_ZONE)


def local_datetime(day, clock_time):
    """Combine a date and a naive time into an aware local datetime."""
    return datetime.combine(day, clock_time, tzinfo=get_local_tz())


def _calculate_age(dob):
    """Calculate age from date of birth."""
    if not dob:
        return None
    today = timezone.localdate()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _count_overdue_months(student):
    """
    Number of distinct months (before the current one) the student still owes
    money for.

    Counting payment *rows* made a student enrolled in three groups with one
    unpaid month look three months overdue in the scanner dossier.
    """
    current_month = timezone.localdate().replace(day=1)
    return Payment.objects.filter(
        student=student,
        month__lt=current_month,
        status__in=['unpaid', 'partial'],
    ).values('month').distinct().count()


def _count_last_month_attendance(student):
    """Count attendance records from last month."""
    now = timezone.localdate()
    first_of_current = now.replace(day=1)
    last_month_end = first_of_current - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    return Attendance.objects.filter(
        student=student,
        session__session_date__gte=last_month_start,
        session__session_date__lte=last_month_end,
    ).count()


def _calculate_attendance_rate(student):
    """
    Percentage of sessions attended this month out of the sessions that
    actually took place in the groups the student is enrolled in.

    Numerator and denominator must describe the *same* set of sessions:
    counting attendance across every group the student ever attended, with no
    upper date bound, produced rates above 100%.
    """
    now = timezone.localdate()
    current_month = now.replace(day=1)
    enrolled_group_ids = list(
        student.group_enrollments.filter(is_active=True).values_list('group_id', flat=True)
    )
    total_sessions = Session.objects.filter(
        group_id__in=enrolled_group_ids,
        session_date__gte=current_month,
        session_date__lte=now,
    ).count()
    if total_sessions == 0:
        return None
    attended = Attendance.objects.filter(
        student=student,
        session__group_id__in=enrolled_group_ids,
        session__session_date__gte=current_month,
        session__session_date__lte=now,
        status__in=['present', 'late'],
    ).count()
    return min(round((attended / total_sessions) * 100, 1), 100.0)


class AttendanceService:
    """
    خدمة تسجيل الحضور - النظام الثابت
    الخوارزمية: 4 خطوات صارمة بدون تعقيدات
    + الكشف الفوري: بمجرد مسح الكود، تظهر حالة الطالب فوراً
    """

    # ثوابت النظام
    STRICT_GRACE_PERIOD_MINUTES = 10  # قاعدة الـ 10 دقائق الصارمة
    EARLY_ARRIVAL_LIMIT_MINUTES = 30  # السماح بالوصول قبل 30 دقيقة

    @staticmethod
    def get_instant_status(student, group):
        """
        الكشف الفوري - Instant Status
        بمجرد مسح الكود، تظهر حالة الطالب فوراً:
        - هل دفع الشهر الجديد؟
        - هل عليه متأخرات؟
        """
        current_month = timezone.localdate().replace(day=1)

        # Read-only: this is a status *probe* run on every scan (including for
        # exempt students), so it must never create a Payment row as a side
        # effect. A missing row simply means "nothing recorded yet" = unpaid.
        current_payment = Payment.objects.filter(
            student=student,
            group=group,
            month=current_month,
        ).first()
        has_paid_current = bool(current_payment and current_payment.status == 'paid')

        # Check arrears (unpaid previous months)
        arrears = Payment.objects.filter(
            student=student,
            group=group,
            month__lt=current_month,
            status__in=['unpaid', 'partial']
        )
        has_arrears = arrears.exists()
        arrears_amount = sum(
            (p.amount_due - p.amount_paid) for p in arrears
        )

        # Get enrollment info
        try:
            enrollment = StudentGroupEnrollment.objects.get(
                student=student, group=group, is_active=True
            )
            financial_status = enrollment.get_financial_status_display()
            is_exempt = enrollment.financial_status == 'exempt'
        except StudentGroupEnrollment.DoesNotExist:
            financial_status = '-'
            is_exempt = False

        # Serialize current_payment to dict to avoid JSON serialization errors
        current_payment_dict = None
        if current_payment:
            current_payment_dict = {
                'payment_id': current_payment.payment_id,
                'amount_due': float(current_payment.amount_due),
                'amount_paid': float(current_payment.amount_paid),
                'status': current_payment.status,
                'status_display': current_payment.get_status_display(),
                'sessions_attended': current_payment.sessions_attended,
                'payment_date': current_payment.payment_date.isoformat() if current_payment.payment_date else None,
            }
        
        return {
            'has_paid_current_month': has_paid_current,
            'current_month_status': current_payment.get_status_display() if current_payment else 'لم يتم إنشاء سجل دفع',
            'has_arrears': has_arrears,
            'arrears_amount': float(arrears_amount),
            'financial_status': financial_status,
            'is_exempt': is_exempt,
            'current_payment': current_payment_dict,
        }

    @staticmethod
    def process_scan(student_code, supervisor):
        """
        معالجة إدخال كود الطالب - النظام المبسط

        الخوارزمية:
        1. جلب الطالب بـ student_code
        2. مطابقة الجدول (الوقت واليوم الحاليين)
        3. قاعدة 10 دقائق صارمة (>10 = BLOCK)
        4. فحص مالي بالحصص لكل مجموعة على حدة (انظر apps.attendance.entitlement)
        + الكشف الفوري للحالة المالية
        """
        # ========================================
        # تنظيف الكود: إزالة المسافات وأي بادئة/لاحقة يضيفها القارئ
        # ========================================
        student_code = str(student_code).strip().strip('*').strip()
        logger.info(f"SCAN_RECEIVED code={repr(student_code)} supervisor={getattr(supervisor, 'id', '?')}")

        # ========================================
        # الخطوة 1: التعريف - جلب الطالب
        # ========================================
        try:
            student = Student.objects.get(
                student_code=student_code,
                is_active=True
            )
        except Student.DoesNotExist:
            return {
                'success': False,
                'message': f'طالب غير موجود بالكود: {student_code}',
                'sound': 'error',
                'severity': 'error',
            }

        # The dossier costs a handful of queries (enrollments, payments,
        # monthly stats). Build it lazily and at most once: every response
        # below that needs it asks for it, nothing pays for it up front.
        dossier_cache = {}

        def dossier():
            if 'value' not in dossier_cache:
                dossier_cache['value'] = AttendanceService.build_student_dossier(student)
            return dossier_cache['value']

        # ========================================
        # الخطوة 2: مطابقة الجدول — جمع كل الحصص المطابقة
        # (Bug 2 fix: collect ALL matching sessions, not just the first)
        # ========================================
        current_time = timezone.now()
        current_day_name = AttendanceService.get_current_day_name()
        current_time_local = timezone.localtime(current_time)

        # جلب كل المجموعات المسجل فيها الطالب
        # ``group__schedules`` is prefetched so the schedule lookup below costs
        # one query for the whole scan instead of one per group.
        enrollments = StudentGroupEnrollment.objects.filter(
            student=student,
            is_active=True,
            group__is_active=True,
            group__deleted_at__isnull=True,
        ).select_related('group', 'group__teacher').prefetch_related('group__schedules')

        # جمع كل المجموعات المطابقة للجدول الآن
        matching_entries = []  # list of (group, enrollment, schedule_dict)

        for enr in enrollments:
            group = enr.group

            # GroupSchedule is the single source of truth; groups that still
            # only have the legacy schedule_day/schedule_time columns are
            # covered by the same helper.
            entry = group.get_schedule_for_day(current_day_name)
            if entry is None or not entry.start_time:
                continue

            schedule_time = entry.start_time
            duration = entry.duration or 120

            session_start = local_datetime(current_time_local.date(), schedule_time)
            session_end = session_start + timedelta(minutes=duration)
            early_window = session_start - timedelta(minutes=AttendanceService.EARLY_ARRIVAL_LIMIT_MINUTES)

            # السماح بالمسح من 30 دقيقة قبل الحصة حتى نهاية الحصة
            if early_window <= current_time_local <= session_end:
                matching_entries.append((group, enr, {'time': schedule_time, 'duration': duration}))

        if not matching_entries:
            rejection = AttendanceService._build_schedule_rejection(
                student, enrollments, current_day_name, current_time_local
            )
            result = {
                'success': False,
                'message': rejection['message'],
                'sound': 'error',
                'error_type': rejection['type'],
                'severity': SEVERITY_MAP.get(rejection['type'], 'error'),
                'student_name': student.full_name,
                'dossier': dossier(),
            }
            # Also check financial status so scanner can show action buttons
            # even when student doesn't have a session today
            for _enr in enrollments:
                fin_check = AttendanceService.check_financial_status(student, _enr.group)
                if not fin_check.get('allowed') and fin_check.get('error_type') == 'payment_required':
                    result['payment_info'] = {
                        'payment_id': fin_check.get('payment_id'),
                        'student_id': fin_check.get('student_id'),
                        'group_id': fin_check.get('group_id'),
                        'amount_due': fin_check.get('amount_due'),
                        'error_type': 'payment_required',
                    }
                    break
            return result

        # ========================================
        # الخطوات 3-5 لكل مجموعة مطابقة
        # ========================================
        newly_registered = []
        already_registered = []
        skipped = []
        combined_instant_status = {}

        for matching_group, enrollment, matched_schedule in matching_entries:
            # الكشف الفوري
            instant_status = AttendanceService.get_instant_status(student, matching_group)
            combined_instant_status[matching_group.group_name] = instant_status

            # قاعدة الـ 10 دقائق الصارمة
            time_check = AttendanceService.check_strict_time(
                current_time,
                matched_schedule['time'],
                matched_schedule['duration']
            )

            if not time_check['allowed']:
                skipped.append({
                    'group_name': matching_group.group_name,
                    'reason': time_check['reason'],
                })
                continue

            # الفحص المالي
            financial_check = AttendanceService.check_financial_status(
                student,
                matching_group
            )

            if not financial_check['allowed']:
                skip_item = {
                    'group_name': matching_group.group_name,
                    'reason': financial_check['reason'],
                    'error_type': financial_check.get('error_type'),
                }
                # Pass payment details so the scanner UI can show action buttons
                if financial_check.get('error_type') == 'payment_required':
                    skip_item['payment_id'] = financial_check.get('payment_id')
                    skip_item['student_id'] = financial_check.get('student_id')
                    skip_item['group_id'] = financial_check.get('group_id')
                    skip_item['amount_due'] = financial_check.get('amount_due')
                skipped.append(skip_item)
                continue

            # التسجيل النهائي — get_or_create للحصة
            # One atomic block per group: the session row, the attendance row
            # and the payment session counter must land together, and two
            # supervisors scanning the same card at once must not leave a
            # half-written group behind when they race on unique_together.
            with transaction.atomic():
                session, session_created = Session.objects.get_or_create(
                    group=matching_group,
                    session_date=timezone.localdate(),
                    defaults={'teacher_attended': False}
                )
                if session_created:
                    from apps.teachers.cycles import assign_to_cycle
                    assign_to_cycle(session)

                if session.is_cancelled:
                    reason = session.cancellation_reason or 'تم إلغاء الحصة'
                    skipped.append({
                        'group_name': matching_group.group_name,
                        'reason': f'الحصة ملغاة — {reason}',
                        'error_type': 'session_cancelled',
                    })
                    continue

                # Bug 1 fix: use get_or_create — repeat scan = success, not error
                attendance, created = Attendance.objects.get_or_create(
                    student=student,
                    session=session,
                    defaults={
                        'scan_time': timezone.now(),
                        'status': time_check['status'],
                        'supervisor': supervisor,
                    }
                )

                if created:
                    AttendanceService.update_payment_sessions(student, matching_group)

            if created:
                newly_registered.append({
                    'group_id': matching_group.group_id,
                    'group_name': matching_group.group_name,
                    'attendance_id': attendance.attendance_id,
                    'status': attendance.status,
                    'status_display': attendance.get_status_display(),
                    'scan_time': attendance.scan_time.isoformat(),
                })
            else:
                already_registered.append({
                    'group_id': matching_group.group_id,
                    'group_name': matching_group.group_name,
                    'attendance_id': attendance.attendance_id,
                    'status': attendance.status,
                    'status_display': attendance.get_status_display(),
                    'scan_time': attendance.scan_time.isoformat(),
                })

        # ========================================
        # بناء الرد — كل التسجيلات تُعتبر نجاح
        # ========================================
        has_new = len(newly_registered) > 0
        has_already = len(already_registered) > 0
        has_skipped = len(skipped) > 0

        # تحديد حالة الرد
        if has_new and has_already:
            status_key = 'registered'
            message = f'مرحباً {student.full_name} — تم تسجيل {len(newly_registered)} حصة، و{len(already_registered)} مسجلة مسبقاً'
            sound = 'success'
        elif has_new:
            group_names = '، '.join(r['group_name'] for r in newly_registered)
            status_key = 'registered'
            message = f'مرحباً {student.full_name} — {group_names}'
            sound = 'success'
        elif has_already:
            status_key = 'already_registered'
            message = f'{student.full_name} — تم تسجيل الحضور مسبقاً'
            sound = 'info'
        elif has_skipped:
            # All groups skipped due to time/financial
            return {
                'success': False,
                'message': f'{student.full_name}: {skipped[0]["reason"]}',
                'sound': 'error',
                'error_type': 'skipped',
                'severity': 'warning',
                'student_name': student.full_name,
                'skipped': skipped,
                'dossier': dossier(),
            }
        else:
            return {
                'success': False,
                'message': f'لا توجد حصة متاحة الآن للطالب {student.full_name}',
                'sound': 'error',
                'error_type': 'no_session',
                'severity': 'info',
                'student_name': student.full_name,
                'dossier': dossier(),
            }

        # الرد الرئيسي (أول مجموعة مسجلة — للتوافق مع الواجهة القديمة)
        first_result = (newly_registered + already_registered)[0]

        logger.info(
            f"SCAN_RESULT code={student.student_code} status={status_key} "
            f"new={len(newly_registered)} already={len(already_registered)} "
            f"skipped={len(skipped)}"
        )

        return {
            'success': True,
            'status': status_key,
            'severity': 'success',
            'message': message,
            'sound': sound,
            'student': {
                'student_id': student.student_id,
                'full_name': student.full_name,
                'student_code': student.student_code,
                'phone': student.student_phone,
            },
            'group': {
                'group_id': first_result['group_id'],
                'group_name': first_result['group_name'],
            },
            'attendance': {
                'attendance_id': first_result['attendance_id'],
                'status': first_result['status'],
                'status_display': first_result['status_display'],
                'scan_time': first_result['scan_time'],
            },
            'newly_registered': newly_registered,
            'already_registered': already_registered,
            'skipped': skipped,
            'instant_status': combined_instant_status.get(first_result['group_name'], {}),
            'dossier': dossier(),
        }
    
    @staticmethod
    def _build_schedule_rejection(student, enrollments, current_day_name, now_local):
        """
        Build a specific, actionable rejection message when no session matches.
        Distinguishes: no groups, wrong day, too early, too late (session ended).
        """
        name = student.full_name
        today_ar = DAY_NAMES_AR.get(current_day_name, current_day_name)

        enrollments = list(enrollments)
        if not enrollments:
            return {
                'type': 'no_groups',
                'message': f'الطالب {name} غير مسجل في أي مجموعة نشطة',
            }

        # Collect all groups and check which are today vs other days.
        # ``get_schedule_for_day`` reads GroupSchedule (all days) and falls back
        # to the legacy columns, so a multi-day group is no longer reported
        # under the wrong day.
        today_groups = []
        for enr in enrollments:
            group = enr.group
            entry = group.get_schedule_for_day(current_day_name)
            if entry and entry.start_time:
                today_groups.append((group, entry.start_time, entry.duration or 120))

        if not today_groups:
            # Student has groups but none scheduled today — show their full
            # weekly schedule, every day of it, in Arabic.
            schedules = []
            for enr in enrollments:
                g = enr.group
                teacher = g.teacher.full_name if g.teacher else ''
                label = f'{g.group_name} ({g.get_schedule_display()}' + (f' - {teacher}' if teacher else '') + ')'
                schedules.append(label)
            schedules_text = ' ، '.join(schedules)
            return {
                'type': 'no_session_today',
                'message': f'الطالب {name} ليس له حصة اليوم ({today_ar}). مواعيده: {schedules_text}',
            }

        # Student has groups today but none match the time window —
        # figure out if we're too early or too late
        earliest_upcoming = None  # (group, mins_until, time_str)
        most_recent_ended = None  # (group, mins_since, time_str)

        for group, sched_time, duration in today_groups:
            session_start = local_datetime(now_local.date(), sched_time)
            session_end = session_start + timedelta(minutes=duration)
            early_window = session_start - timedelta(minutes=AttendanceService.EARLY_ARRIVAL_LIMIT_MINUTES)

            if now_local < early_window:
                mins = int((session_start - now_local).total_seconds() / 60)
                if earliest_upcoming is None or mins < earliest_upcoming[1]:
                    earliest_upcoming = (group, mins, sched_time.strftime('%I:%M %p'))
            elif now_local > session_end:
                mins = int((now_local - session_start).total_seconds() / 60)
                if most_recent_ended is None or mins < most_recent_ended[1]:
                    most_recent_ended = (group, mins, sched_time.strftime('%I:%M %p'))

        if earliest_upcoming:
            group, mins, time_str = earliest_upcoming
            return {
                'type': 'too_early',
                'message': f'مبكر جداً! حصة {group.group_name} للطالب {name} تبدأ الساعة {time_str} (بعد {mins} دقيقة)',
            }

        if most_recent_ended:
            group, mins, time_str = most_recent_ended
            return {
                'type': 'too_late',
                'message': f'الحصة انتهت! حصة {group.group_name} للطالب {name} كانت الساعة {time_str} (منذ {mins} دقيقة)',
            }

        return {
            'type': 'wrong_schedule',
            'message': f'لا توجد حصة متاحة الآن للطالب {name}',
        }

    @staticmethod
    def get_current_day_name():
        """
        الحصول على اسم اليوم الحالي بالإنجليزي
        Python's weekday(): Monday=0, Tuesday=1, ..., Sunday=6
        Uses localtime() to get correct day in Africa/Cairo timezone.
        """
        days_map = {
            0: 'Monday',
            1: 'Tuesday',
            2: 'Wednesday',
            3: 'Thursday',
            4: 'Friday',
            5: 'Saturday',
            6: 'Sunday',
        }
        today = timezone.localtime().weekday()
        return days_map.get(today, '')

    @staticmethod
    def check_strict_time(scan_time, schedule_time, duration_minutes=120):
        """
        الخطوة 3: قاعدة الـ 10 دقائق الصارمة

        القواعد:
        - الوقت الفعلي مقارنة بالجدول الرسمي
        - في الموعد أو قبله: حاضر
        - من دقيقة إلى 10 دقائق تأخير: قبول مع تسجيل "متأخر"
        - >10 دقائق: رفض كامل (BLOCK)
        - يراعي مدة الحصة (بعد انتهاء الحصة = رفض)

        The 10-minute window used to be recorded as ``present`` as well, which
        made the ``late`` status unreachable and left every "late" counter in
        the dashboard, the reports and the CSV export permanently zero.
        """
        # تحويل scan_time إلى التوقيت المحلي للمقارنة مع schedule_time
        scan_time_local = scan_time.astimezone(get_local_tz())

        # إنشاء session_start في نفس التوقيت المحلي
        session_start = local_datetime(scan_time_local.date(), schedule_time)
        session_end = session_start + timedelta(minutes=duration_minutes)

        # حساب الفرق بالدقائق
        diff = scan_time_local - session_start
        diff_minutes = diff.total_seconds() / 60

        # رفض إذا وصل بعد انتهاء الحصة
        if scan_time_local > session_end:
            return {
                'allowed': False,
                'reason': f'الحصة انتهت. كانت من {schedule_time.strftime("%I:%M %p")} إلى {session_end.strftime("%I:%M %p")}',
                'error_type': 'session_ended'
            }

        # السماح بالوصول المبكر (30 دقيقة قبل الموعد)
        if diff_minutes < -AttendanceService.EARLY_ARRIVAL_LIMIT_MINUTES:
            return {
                'allowed': False,
                'reason': f'وصلت مبكراً جداً. الموعد: {schedule_time.strftime("%I:%M %p")}',
                'error_type': 'too_early'
            }

        # القاعدة الصارمة: أكثر من 10 دقائق = رفض
        if diff_minutes > AttendanceService.STRICT_GRACE_PERIOD_MINUTES:
            return {
                'allowed': False,
                'reason': f'ممنوع الدخول - تأخرت {int(diff_minutes)} دقيقة (الحد المسموح: 10 دقائق)',
                'error_type': 'too_late'
            }

        # قبول: في الموعد (حاضر) أو في حدود الـ 10 دقائق (متأخر)
        minutes_late = max(0, int(diff_minutes))
        return {
            'allowed': True,
            'status': 'late' if minutes_late >= 1 else 'present',
            'minutes_late': minutes_late,
        }
    
    @staticmethod
    def check_financial_status(student, group):
        """
        الخطوة 4: فحص الحالة المالية — بالحصص، لكل (طالب × مجموعة) على حدة.

        غلاف رقيق حول ``apps.attendance.entitlement.evaluate`` — القرار
        الفعلي منطقي بحت وقابل للاختبار هناك بمعزل عن قاعدة البيانات
        والسكانر. الاسم والشكل المُرجَع أُبقيا كما هما تمامًا لأن
        ``process_scan`` وعشرات الاختبارات يعتمدون عليهما.
        """
        from apps.teachers.cycles import open_cycle_for
        from . import entitlement

        try:
            enrollment = StudentGroupEnrollment.objects.select_related('group').get(
                student=student, group=group, is_active=True,
            )
        except StudentGroupEnrollment.DoesNotExist:
            return {
                'allowed': False,
                'reason': 'ممنوع الدخول: غير مسجل في هذه المجموعة',
                'error_type': 'not_enrolled',
            }

        if not group.sessions_per_month:
            cycle = None
        else:
            cycle = (
                group.cycles.filter(closed_on__isnull=True).order_by('-index').first()
                or open_cycle_for(group)
            )

        return entitlement.evaluate(enrollment, cycle)

    @staticmethod
    def check_exception_status(student, group, exception_type='payment'):
        """
        Check if the student has an active exception for the given group.

        Returns the ExceptionRecord if found and active, else None.
        Used by both the financial check (payment exception) and
        the time check (late-arrival exception).
        """
        from .models import ExceptionRecord
        today = timezone.localdate()

        exception = ExceptionRecord.objects.filter(
            student=student,
            group=group,
            exception_type=exception_type,
            is_active=True,
            created_at__date=today,
        ).order_by('-created_at').first()

        return exception

    @staticmethod
    def apply_late_exception(student, group, session, exception_record):
        """
        Apply a late-arrival exception: create an attendance record
        with status='exception' even though the student arrived late.
        """
        attendance, created = Attendance.objects.get_or_create(
            student=student,
            session=session,
            defaults={
                'scan_time': timezone.now(),
                'status': 'exception',
                'supervisor': exception_record.approved_by,
                'exception_record': exception_record,
            }
        )
        if not created:
            attendance.status = 'exception'
            attendance.exception_record = exception_record
            attendance.save(update_fields=['status', 'exception_record'])

        AttendanceService.update_payment_sessions(student, group)
        return attendance
    
    @staticmethod
    def build_student_dossier(student):
        """
        بناء ملف الطالب الشامل — يُعرض بعد كل مسح ناجح
        يشمل: البيانات الشخصية، المجموعات، حالة الدفع، إحصائيات الحضور
        """
        current_month = timezone.localdate().replace(day=1)

        enrollments = list(
            student.group_enrollments.filter(
                is_active=True,
                group__is_active=True,
                group__deleted_at__isnull=True,
            )
            .select_related('group', 'group__teacher')
            .prefetch_related('group__schedules')
        )

        # الدورة المفتوحة الحالية لكل مجموعة، ثم مدفوعات تلك الدورات — كل ذلك
        # في استعلامين فقط (كان استعلاماً لكل مجموعة داخل الحلقة).
        group_ids = [enr.group_id for enr in enrollments]
        from apps.teachers.models import GroupCycle
        open_cycles_by_group = {
            c.group_id: c
            for c in GroupCycle.objects.filter(group_id__in=group_ids, closed_on__isnull=True)
        }
        payments_by_group = {
            p.group_id: p
            for p in Payment.objects.filter(
                student=student,
                group_id__in=group_ids,
                cycle_id__in=[c.cycle_id for c in open_cycles_by_group.values()],
            )
        }

        # كل التسجيلات النشطة مع معلومات الدفع للشهر الحالي
        enrollments_data = []
        for enr in enrollments:
            group = enr.group
            payment = payments_by_group.get(group.pk)
            cycle = open_cycles_by_group.get(group.pk)

            if enr.financial_status == 'exempt':
                pay_status = 'exempt'
                pay_status_display = 'إعفاء كامل'
                amount_due = 0.0
                amount_paid = 0.0
                remaining = 0.0
            elif payment:
                pay_status = payment.status
                pay_status_display = payment.get_status_display()
                amount_due = float(payment.amount_due)
                amount_paid = float(payment.amount_paid)
                remaining = float(payment.amount_due - payment.amount_paid)
            else:
                fee = student.get_monthly_fee_for_group(group)
                pay_status = 'unpaid'
                pay_status_display = 'غير مدفوع'
                amount_due = float(fee)
                amount_paid = 0.0
                remaining = float(fee)

            # معلومات الجدول — كل أيام المجموعة بالعربية.
            # الكود القديم كان يفحص ``SCHEDULE_DAY_CHOICES`` وهو اسم غير موجود
            # (الصحيح ``DAYS_CHOICES``) فكان الفرع لا يعمل أبداً وتظهر
            # أسماء الأيام بالإنجليزية في ملف الطالب.
            entries = group.get_schedule_entries()
            schedule_str = group.get_schedule_display() if entries else '-'
            first_entry = entries[0] if entries else None

            enrollments_data.append({
                'group_id': group.group_id,
                'group_name': group.group_name,
                'teacher_name': group.teacher.full_name if group.teacher else '—',
                'schedule': schedule_str,
                'schedule_day_en': first_entry.day_of_week if first_entry else '',
                'schedule_day_ar': first_entry.get_day_display() if first_entry else '',
                'schedule_time': first_entry.start_time.strftime('%H:%M') if first_entry else '',
                'schedule_days': [
                    {
                        'day_en': e.day_of_week,
                        'day_ar': e.get_day_display(),
                        'time': e.start_time.strftime('%H:%M'),
                    }
                    for e in entries
                ],
                'financial_status': enr.get_financial_status_display(),
                'financial_status_code': enr.financial_status,
                'payment': {
                    'status': pay_status,
                    'status_display': pay_status_display,
                    'amount_due': amount_due,
                    'amount_paid': amount_paid,
                    'remaining': remaining,
                },
                'entitlement': {
                    'cycle_index': cycle.index if cycle else None,
                    'sessions_consumed': payment.sessions_attended if payment else 0,
                    'sessions_total': (
                        payment.sessions_total if payment
                        else (cycle.sessions_planned if cycle else None)
                    ),
                },
            })

        # إحصائيات الحضور هذا الشهر
        month_attendances = Attendance.objects.filter(
            student=student,
            session__session_date__gte=current_month
        )
        total_this_month = month_attendances.count()
        last_att = month_attendances.order_by('-scan_time').first()
        last_scan_iso = (
            timezone.localtime(last_att.scan_time).isoformat()
            if last_att else None
        )

        return {
            'student_id': student.student_id,
            'student_code': student.student_code,
            'full_name': student.full_name,
            'gender': student.get_gender_display(),
            'education': student.get_education_display_full(),
            'student_phone': student.student_phone or None,
            'parent_phone': student.parent_phone or None,
            # Dial-ready form for wa.me — computed server-side by the single
            # implementation (apps.students.utils.whatsapp_number) instead of
            # the scanner re-deriving it in JS and drifting from it.
            'parent_whatsapp': student.parent_whatsapp or None,
            'parent_name': student.parent_name or None,
            'personal': {
                'address': student.address or '',
                'date_of_birth': student.date_of_birth.isoformat() if student.date_of_birth else None,
                'age': _calculate_age(student.date_of_birth),
                'school_name': student.school_name or '',
                'parent_name': student.parent_name or '',
                'registration_date': student.created_at.strftime('%Y-%m-%d') if student.created_at else None,
            },
            'enrollments': enrollments_data,
            'financial_summary': {
                'total_due': sum(e['payment']['amount_due'] for e in enrollments_data),
                'total_paid': sum(e['payment']['amount_paid'] for e in enrollments_data),
                'total_remaining': sum(e['payment']['remaining'] for e in enrollments_data),
                'overdue_months': _count_overdue_months(student),
            },
            'attendance_month': {
                'total': total_this_month,
                'last_scan': last_scan_iso,
                'last_scan_group': last_att.session.group.group_name if last_att else None,
                'last_month': _count_last_month_attendance(student),
                'rate': _calculate_attendance_rate(student),
            },
        }

    @staticmethod
    def update_payment_sessions(student, group):
        """
        Update ``sessions_attended`` on this student's Payment for the
        group's **current cycle** — not the calendar month. Absences (auto-
        marked or manual) still count, so a missed session still burns
        entitlement exactly like an attended one.

        If this is the student's first consumed session of the cycle, also
        stamps the entitlement anchor (``entitlement_start_session`` /
        ``entitlement_start_seq``) and prices the row via
        :mod:`apps.payments.pricing` (pro-rated for a mid-cycle join).
        Never called for a group with no cycle billing
        (``sessions_per_month == 0``) — callers check that first.
        """
        from apps.teachers.cycles import open_cycle_for
        from apps.payments.pricing import prorated_fee, entitled_sessions

        if not group.sessions_per_month:
            return

        cycle = open_cycle_for(group)

        sessions_count = Attendance.objects.filter(
            student=student,
            session__cycle=cycle,
            session__is_cancelled=False,
        ).count()

        try:
            enrollment = StudentGroupEnrollment.objects.get(student=student, group=group)
        except StudentGroupEnrollment.DoesNotExist:
            enrollment = None

        payment = Payment.objects.filter(student=student, cycle=cycle).first()
        if payment is None:
            first = (
                Attendance.objects.filter(
                    student=student, session__cycle=cycle, session__is_cancelled=False,
                )
                .exclude(status='absent')
                .order_by('session__sequence_in_cycle')
                .select_related('session')
                .first()
            )
            first_seq = first.session.sequence_in_cycle if first else 1
            payment = Payment.objects.create(
                student=student,
                group=group,
                cycle=cycle,
                month=cycle.started_on.replace(day=1) if cycle.started_on else timezone.localdate().replace(day=1),
                amount_due=prorated_fee(
                    enrollment, cycle_size=cycle.sessions_planned,
                    first_sequence=first_seq, group=group,
                ) if enrollment else 0,
                sessions_attended=sessions_count,
                sessions_total=entitled_sessions(
                    cycle_size=cycle.sessions_planned, first_sequence=first_seq,
                ),
                entitlement_start_session=first.session if first else None,
                entitlement_start_seq=first_seq if first else None,
            )
        else:
            payment.sessions_attended = sessions_count
            payment.save(update_fields=['sessions_attended'])

    # ``update_billing_cycle`` used to live here. It was never called by
    # anything and diverged from ``apps.attendance.tasks.roll_group_cycles``
    # (which reimplements the same rule at the group level, since every
    # student on a group shares one cycle). The Celery task is now the
    # single implementation of cycle-completion.
