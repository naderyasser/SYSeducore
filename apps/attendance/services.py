import logging
from datetime import datetime, timedelta
from django.utils import timezone
from .models import Attendance, Session
from apps.students.models import Student, StudentGroupEnrollment
from apps.payments.models import Payment
from apps.teachers.models import GroupSchedule

logger = logging.getLogger('attendance')

# Arabic day names for user-facing messages
DAY_NAMES_AR = {
    'Saturday': 'السبت', 'Sunday': 'الأحد', 'Monday': 'الاثنين',
    'Tuesday': 'الثلاثاء', 'Wednesday': 'الأربعاء',
    'Thursday': 'الخميس', 'Friday': 'الجمعة',
}

# Maps error_type → UI severity for the frontend card color
SEVERITY_MAP = {
    'not_found': 'error',
    'invalid_code': 'error',
    'subscription_expired': 'error',
    'payment_required': 'warning',
    'sessions_exhausted': 'warning',
    'too_early': 'info',
    'too_late': 'warning',
    'no_session_today': 'info',
    'no_groups': 'warning',
    'wrong_schedule': 'info',
    'skipped': 'warning',
    'no_session': 'info',
}


def _calculate_age(dob):
    """Calculate age from date of birth."""
    if not dob:
        return None
    today = timezone.localtime().date()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _count_overdue_months(student):
    """Count months with unpaid/partial payment before current month."""
    current_month = timezone.localtime().date().replace(day=1)
    return Payment.objects.filter(
        student=student,
        month__lt=current_month,
        status__in=['unpaid', 'partial'],
    ).count()


def _count_last_month_attendance(student):
    """Count attendance records from last month."""
    now = timezone.localtime().date()
    first_of_current = now.replace(day=1)
    last_month_end = first_of_current - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    return Attendance.objects.filter(
        student=student,
        session__session_date__gte=last_month_start,
        session__session_date__lte=last_month_end,
    ).count()


def _calculate_attendance_rate(student):
    """Percentage of sessions attended this month out of sessions that occurred."""
    now = timezone.localtime().date()
    current_month = now.replace(day=1)
    enrolled_group_ids = student.group_enrollments.filter(
        is_active=True
    ).values_list('group_id', flat=True)
    total_sessions = Session.objects.filter(
        group_id__in=enrolled_group_ids,
        session_date__gte=current_month,
        session_date__lte=now,
    ).count()
    if total_sessions == 0:
        return None
    attended = Attendance.objects.filter(
        student=student,
        session__session_date__gte=current_month,
        status__in=['present', 'late'],
    ).count()
    return round((attended / total_sessions) * 100, 1)


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
        current_month = timezone.localtime().date().replace(day=1)

        # Check current month payment — auto-create if missing so the
        # scanner always has a Payment row to evaluate.
        current_payment, _created = Payment.objects.get_or_create(
            student=student,
            group=group,
            month=current_month,
            defaults={
                'amount_due': student.get_monthly_fee_for_group(group),
                'status': 'unpaid',
            },
        )
        has_paid_current = current_payment.status == 'paid'

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

        الخوارزمية (5 خطوات):
        1. جلب الطالب بـ student_code
        2. التحقق من صلاحية الاشتراك (30 يوم)
        3. مطابقة الجدول (الوقت واليوم الحاليين)
        4. قاعدة 10 دقائق صارمة (>10 = BLOCK)
        5. فحص مالي
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
            student = Student.objects.prefetch_related('groups').get(
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

        # Build dossier ONCE — included in every subsequent response
        dossier = AttendanceService.build_student_dossier(student)

        # ========================================
        # الخطوة 1.5: التحقق من صلاحية الاشتراك
        # ========================================
        if not student.is_subscription_active():
            subscription_status = student.get_subscription_status()
            days_expired = abs(subscription_status.get('days_remaining', 0))
            return {
                'success': False,
                'message': f'اشتراك الطالب {student.full_name} منتهي منذ {days_expired} يوم — يجب التجديد قبل تسجيل الحضور',
                'sound': 'error',
                'error_type': 'subscription_expired',
                'severity': 'error',
                'student_name': student.full_name,
                'subscription_status': subscription_status,
                'dossier': dossier,
            }

        # ========================================
        # الخطوة 2: مطابقة الجدول — جمع كل الحصص المطابقة
        # (Bug 2 fix: collect ALL matching sessions, not just the first)
        # ========================================
        current_time = timezone.now()
        current_day_name = AttendanceService.get_current_day_name()

        from django.conf import settings
        import pytz
        local_tz = pytz.timezone(settings.TIME_ZONE)
        current_time_local = current_time.astimezone(local_tz)

        # جلب كل المجموعات المسجل فيها الطالب
        enrollments = StudentGroupEnrollment.objects.filter(
            student=student,
            is_active=True
        ).select_related('group')

        # جمع كل المجموعات المطابقة للجدول الآن
        matching_entries = []  # list of (group, enrollment, schedule_dict)

        for enr in enrollments:
            group = enr.group

            # Try GroupSchedule first
            try:
                schedule = GroupSchedule.objects.get(group=group, day_of_week=current_day_name)
                schedule_time = schedule.start_time
                duration = schedule.duration
            except GroupSchedule.DoesNotExist:
                # Fallback to legacy fields
                if group.schedule_day != current_day_name:
                    continue
                schedule_time = group.schedule_time
                duration = group.duration_minutes

            if not schedule_time:
                continue

            session_start = local_tz.localize(
                datetime.combine(current_time_local.date(), schedule_time)
            )
            session_end = session_start + timedelta(minutes=duration)
            early_window = session_start - timedelta(minutes=AttendanceService.EARLY_ARRIVAL_LIMIT_MINUTES)

            # السماح بالمسح من 30 دقيقة قبل الحصة حتى نهاية الحصة
            if early_window <= current_time_local <= session_end:
                matching_entries.append((group, enr, {'time': schedule_time, 'duration': duration}))

        if not matching_entries:
            rejection = AttendanceService._build_schedule_rejection(
                student, enrollments, current_day_name, current_time_local, local_tz
            )
            result = {
                'success': False,
                'message': rejection['message'],
                'sound': 'error',
                'error_type': rejection['type'],
                'severity': SEVERITY_MAP.get(rejection['type'], 'error'),
                'student_name': student.full_name,
                'dossier': dossier,
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
            session, _ = Session.objects.get_or_create(
                group=matching_group,
                session_date=timezone.localtime().date(),
                defaults={'teacher_attended': False}
            )

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
                'dossier': dossier,
            }
        else:
            return {
                'success': False,
                'message': f'لا توجد حصة متاحة الآن للطالب {student.full_name}',
                'sound': 'error',
                'error_type': 'no_session',
                'severity': 'info',
                'student_name': student.full_name,
                'dossier': dossier,
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
            'dossier': dossier,
        }
    
    @staticmethod
    def _build_schedule_rejection(student, enrollments, current_day_name, now_local, local_tz):
        """
        Build a specific, actionable rejection message when no session matches.
        Distinguishes: no groups, wrong day, too early, too late (session ended).
        """
        name = student.full_name
        today_ar = DAY_NAMES_AR.get(current_day_name, current_day_name)

        if not enrollments.exists():
            return {
                'type': 'no_groups',
                'message': f'الطالب {name} غير مسجل في أي مجموعة نشطة',
            }

        # Collect all groups and check which are today vs other days
        today_groups = []
        other_groups = []
        for enr in enrollments:
            group = enr.group
            # Check GroupSchedule first, then legacy field
            try:
                schedule = GroupSchedule.objects.get(group=group, day_of_week=current_day_name)
                today_groups.append((group, schedule.start_time, schedule.duration))
            except GroupSchedule.DoesNotExist:
                if group.schedule_day == current_day_name and group.schedule_time:
                    today_groups.append((group, group.schedule_time, group.duration_minutes or 120))
                else:
                    other_groups.append(group)

        if not today_groups:
            # Student has groups but none scheduled today — show their schedule
            schedules = []
            for enr in enrollments:
                g = enr.group
                day_ar = DAY_NAMES_AR.get(g.schedule_day, g.schedule_day)
                time_str = g.schedule_time.strftime('%I:%M %p') if g.schedule_time else ''
                teacher = g.teacher.full_name if g.teacher else ''
                label = f'{g.group_name} ({day_ar} {time_str}' + (f' - {teacher}' if teacher else '') + ')'
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
            session_start = local_tz.localize(
                datetime.combine(now_local.date(), sched_time)
            )
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
        - ≤10 دقائق: قبول (حاضر)
        - >10 دقائق: رفض كامل (BLOCK)
        - لا يوجد "تأخير"، فقط قبول أو رفض
        - يراعي مدة الحصة (بعد انتهاء الحصة = رفض)
        """
        # تحويل scan_time إلى التوقيت المحلي للمقارنة مع schedule_time
        from django.conf import settings
        import pytz
        
        local_tz = pytz.timezone(settings.TIME_ZONE)
        scan_time_local = scan_time.astimezone(local_tz)
        
        # إنشاء session_start في نفس التوقيت المحلي
        session_start = local_tz.localize(
            datetime.combine(scan_time_local.date(), schedule_time)
        )
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

        # قبول: في الموعد أو في حدود الـ 10 دقائق
        return {
            'allowed': True,
            'status': 'present',  # لا يوجد late، فقط present
            'minutes_late': max(0, int(diff_minutes))
        }
    
    @staticmethod
    def is_student_first_month_in_group(student, group):
        """
        تحديد هل هذا هو الشهر الأول للطالب في مجموعة معينة
        """
        current_month = timezone.localtime().date().replace(day=1)

        # البحث عن أول حضور للطالب في هذه المجموعة
        first_attendance = Attendance.objects.filter(
            student=student,
            session__group=group
        ).order_by('scan_time').first()

        if not first_attendance:
            # لم يسجل حضور من قبل في هذه المجموعة = شهر أول
            return True

        # تاريخ أول حضور
        first_month = first_attendance.scan_time.date().replace(day=1)

        # إذا كان أول حضور في نفس الشهر الحالي = شهر أول
        return first_month == current_month
    
    @staticmethod
    def check_financial_status(student, group):
        """
        الخطوة 4: فحص الحالة المالية
        يتحقق من الحالة المالية للطالب في المجموعة المحددة
        """
        from django.conf import settings as django_settings

        # جلب معلومات التسجيل في المجموعة
        try:
            enrollment = StudentGroupEnrollment.objects.get(
                student=student,
                group=group,
                is_active=True
            )
        except StudentGroupEnrollment.DoesNotExist:
            return {
                'allowed': False,
                'reason': 'ممنوع الدخول: غير مسجل في هذه المجموعة',
                'error_type': 'not_enrolled'
            }

        # الطلاب المعفيين دائماً مسموح لهم
        if enrollment.financial_status == 'exempt':
            return {'allowed': True, 'exempt': True}

        # الحصول على الشهر الحالي
        current_month = timezone.localtime().date().replace(day=1)

        # عدد الحصص المسجلة هذا الشهر لهذه المجموعة فقط
        sessions_count = Attendance.objects.filter(
            student=student,
            session__group=group,
            session__session_date__gte=current_month
        ).count()

        # فحص هل هو الشهر الأول في هذه المجموعة
        is_first_month = AttendanceService.is_student_first_month_in_group(student, group)

        # القاعدة:
        # - الشهر الأول مع تفعيل الدفع الصارم: لازم يدفع قبل الدخول (0 حصص سماح)
        # - الشهر الأول بدون دفع صارم: يدخل حصتين قبل الدفع (2 حصص سماح)
        # - الشهور التالية: يدخل حصتين قبل الدفع (2 حصص سماح)
        strict_first_month = getattr(django_settings, 'ENABLE_FIRST_MONTH_STRICT_PAYMENT', True)
        if is_first_month and strict_first_month:
            allowed_sessions = 0
        else:
            allowed_sessions = 2

        # التحقق من استنفاد الحصص الشهرية
        sessions_limit = group.sessions_per_month
        if sessions_count >= sessions_limit:
            return {
                'allowed': False,
                'reason': f'تم استنفاد جميع الحصص ({sessions_limit} حصة) لهذا الشهر. يرجى تجديد الاشتراك.',
                'error_type': 'sessions_exhausted',
                'sessions_attended': sessions_count,
                'sessions_limit': sessions_limit,
            }

        # منع الدخول بعد الحصة المسموح إذا لم يدفع
        if sessions_count >= allowed_sessions:
            # ── Check active payment exceptions first ──
            exception = AttendanceService.check_exception_status(
                student, group, exception_type='payment'
            )
            if exception:
                return {
                    'allowed': True,
                    'exception_applied': True,
                    'exception_id': exception.exception_id,
                    'exception_reason': exception.reason_display,
                }

            # ── Check grace period ──
            today = timezone.localtime().date()
            if enrollment.grace_until and enrollment.grace_until >= today:
                return {
                    'allowed': True,
                    'grace_period': True,
                    'grace_until': enrollment.grace_until.isoformat(),
                }

            # get_or_create guarantees a Payment row exists for this
            # student+group+month so the scanner never fails with a
            # DoesNotExist just because no one opened the payment list.
            payment, _p_created = Payment.objects.get_or_create(
                student=student,
                group=group,
                month=current_month,
                defaults={
                    'amount_due': student.get_monthly_fee_for_group(group),
                    'status': 'unpaid',
                },
            )
            if payment.status != 'paid':
                reason = 'ممنوع الدخول: الدفع مطلوب'
                if is_first_month:
                    reason += ' (الشهر الأول)'
                return {
                    'allowed': False,
                    'reason': reason,
                    'error_type': 'payment_required',
                    'payment_id': payment.payment_id,
                    'student_id': student.student_id,
                    'group_id': group.group_id,
                    'amount_due': float(payment.amount_due),
                }

        return {'allowed': True}

    @staticmethod
    def check_exception_status(student, group, exception_type='payment'):
        """
        Check if the student has an active exception for the given group.

        Returns the ExceptionRecord if found and active, else None.
        Used by both the financial check (payment exception) and
        the time check (late-arrival exception).
        """
        from .models import ExceptionRecord
        today = timezone.localtime().date()

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
        now = timezone.localtime()
        current_month = now.date().replace(day=1)

        # كل التسجيلات النشطة مع معلومات الدفع للشهر الحالي
        enrollments_data = []
        for enr in student.group_enrollments.filter(
            is_active=True
        ).select_related('group', 'group__teacher'):
            group = enr.group
            payment = Payment.objects.filter(
                student=student, group=group, month=current_month
            ).first()

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

            # معلومات الجدول
            schedule_str = '-'
            if group.schedule_time:
                day_display = dict(group.SCHEDULE_DAY_CHOICES).get(
                    group.schedule_day, group.schedule_day
                ) if hasattr(group, 'SCHEDULE_DAY_CHOICES') else group.schedule_day
                schedule_str = f"{day_display} {group.schedule_time.strftime('%I:%M %p')}"

            enrollments_data.append({
                'group_id': group.group_id,
                'group_name': group.group_name,
                'teacher_name': group.teacher.full_name if group.teacher else '—',
                'schedule': schedule_str,
                'schedule_day_en': group.schedule_day,
                'schedule_day_ar': DAY_NAMES_AR.get(group.schedule_day, group.schedule_day),
                'schedule_time': group.schedule_time.strftime('%H:%M') if group.schedule_time else '',
                'financial_status': enr.get_financial_status_display(),
                'financial_status_code': enr.financial_status,
                'payment': {
                    'status': pay_status,
                    'status_display': pay_status_display,
                    'amount_due': amount_due,
                    'amount_paid': amount_paid,
                    'remaining': remaining,
                },
            })

        # حالة الاشتراك
        sub_status = student.get_subscription_status()

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
            'parent_name': student.parent_name or None,
            'personal': {
                'address': student.address or '',
                'date_of_birth': student.date_of_birth.isoformat() if student.date_of_birth else None,
                'age': _calculate_age(student.date_of_birth),
                'school_name': student.school_name or '',
                'parent_name': student.parent_name or '',
                'registration_date': student.created_at.strftime('%Y-%m-%d') if student.created_at else None,
            },
            'subscription': {
                'status': sub_status.get('status'),
                'status_display': sub_status.get('message'),
                'days_remaining': sub_status.get('days_remaining'),
                'expiry_date': (
                    student.subscription_expiry_date.isoformat()
                    if student.subscription_expiry_date else None
                ),
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
        Update sessions_attended on the Payment record.
        Now includes absent records (auto-marked or manual) so that
        missed sessions count toward the billing cycle.

        Total sessions: sum of present + late + absent + exception.
        """
        current_month = timezone.localtime().date().replace(day=1)

        sessions_count = Attendance.objects.filter(
            student=student,
            session__group=group,
            session__session_date__gte=current_month,
        ).count()

        payment, created = Payment.objects.get_or_create(
            student=student,
            group=group,
            month=current_month,
            defaults={
                'amount_due': student.get_monthly_fee_for_group(group),
                'sessions_attended': sessions_count,
                'sessions_total': group.sessions_per_month,
            }
        )

        if not created:
            payment.sessions_attended = sessions_count
            payment.save(update_fields=['sessions_attended'])

    @staticmethod
    def update_billing_cycle(student, group):
        """
        Check whether the billing cycle for this student+group is complete.
        If all sessions for the cycle have been used (attended + absent),
        mark the payment as billing_cycle_completed.

        Also updates StudentGroupEnrollment cycle dates.
        """
        from apps.students.models import StudentGroupEnrollment

        current_month = timezone.localtime().date().replace(day=1)

        try:
            enrollment = StudentGroupEnrollment.objects.get(
                student=student, group=group, is_active=True,
            )
        except StudentGroupEnrollment.DoesNotExist:
            return

        sessions_per_cycle = enrollment.sessions_per_cycle or group.sessions_per_month
        if sessions_per_cycle <= 0:
            sessions_per_cycle = group.sessions_per_month or 4

        sessions_count = Attendance.objects.filter(
            student=student,
            session__group=group,
            session__session_date__gte=(enrollment.cycle_start_date or current_month),
        ).count()

        if sessions_count >= sessions_per_cycle:
            payment = Payment.objects.filter(
                student=student, group=group, month=current_month,
            ).first()
            if payment and not payment.billing_cycle_completed:
                payment.billing_cycle_completed = True
                payment.save(update_fields=['billing_cycle_completed'])
