from datetime import datetime, timedelta
from django.utils import timezone
from .models import Attendance, Session
from apps.students.models import Student, StudentGroupEnrollment
from apps.payments.models import Payment
from apps.teachers.models import GroupSchedule


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
        current_month = timezone.now().date().replace(day=1)

        # Check current month payment
        current_payment = None
        has_paid_current = False
        try:
            current_payment = Payment.objects.get(
                student=student,
                group=group,
                month=current_month
            )
            has_paid_current = current_payment.status == 'paid'
        except Payment.DoesNotExist:
            has_paid_current = False

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
                'message': 'كود غير صالح',
                'sound': 'error'
            }

        # ========================================
        # الخطوة 1.5: التحقق من صلاحية الاشتراك
        # ========================================
        if not student.is_subscription_active():
            subscription_status = student.get_subscription_status()
            return {
                'success': False,
                'message': f'عفواً، اشتراك الطالب منتهي. {subscription_status["message"]}',
                'sound': 'error',
                'error_type': 'subscription_expired',
                'student_name': student.full_name,
                'subscription_status': subscription_status
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
            return {
                'success': False,
                'message': 'ممنوع الدخول: مجموعة خاطئة أو لا توجد حصة الآن',
                'sound': 'error',
                'error_type': 'wrong_schedule'
            }

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
                skipped.append({
                    'group_name': matching_group.group_name,
                    'reason': financial_check['reason'],
                })
                continue

            # التسجيل النهائي — get_or_create للحصة
            session, _ = Session.objects.get_or_create(
                group=matching_group,
                session_date=timezone.now().date(),
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
                'message': skipped[0]['reason'],
                'sound': 'error',
                'error_type': 'skipped',
                'student_name': student.full_name,
                'skipped': skipped,
            }
        else:
            return {
                'success': False,
                'message': 'لا توجد حصة متاحة الآن',
                'sound': 'error',
                'error_type': 'no_session'
            }

        # الرد الرئيسي (أول مجموعة مسجلة — للتوافق مع الواجهة القديمة)
        first_result = (newly_registered + already_registered)[0]

        return {
            'success': True,
            'status': status_key,
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
        }
    
    @staticmethod
    def get_current_day_name():
        """
        الحصول على اسم اليوم الحالي بالإنجليزي
        Python's weekday(): Monday=0, Tuesday=1, ..., Sunday=6
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
        today = timezone.now().weekday()
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
        current_month = timezone.now().date().replace(day=1)

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
        current_month = timezone.now().date().replace(day=1)

        # عدد الحصص المسجلة هذا الشهر لهذه المجموعة فقط
        sessions_count = Attendance.objects.filter(
            student=student,
            session__group=group,
            session__session_date__gte=current_month
        ).count()

        # فحص هل هو الشهر الأول في هذه المجموعة
        is_first_month = AttendanceService.is_student_first_month_in_group(student, group)

        # القاعدة:
        # - الشهر الأول: لازم يدفع قبل الدخول (0 حصص سماح)
        # - الشهور التالية: يدخل حصتين قبل الدفع (2 حصص سماح)
        allowed_sessions = 0 if is_first_month else 2

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
            try:
                payment = Payment.objects.get(
                    student=student,
                    group=group,
                    month=current_month
                )
                if payment.status != 'paid':
                    reason = 'ممنوع الدخول: الدفع مطلوب'
                    if is_first_month:
                        reason += ' (الشهر الأول)'
                    return {
                        'allowed': False,
                        'reason': reason,
                        'error_type': 'payment_required'
                    }
            except Payment.DoesNotExist:
                reason = 'ممنوع الدخول: الدفع مطلوب'
                if is_first_month:
                    reason += ' (الشهر الأول)'
                return {
                    'allowed': False,
                    'reason': reason,
                    'error_type': 'payment_required'
                }

        return {'allowed': True}
    
    @staticmethod
    def update_payment_sessions(student, group):
        """
        تحديث عدد الحصص في سجل الدفع لمجموعة معينة
        """
        current_month = timezone.now().date().replace(day=1)

        # عدد الحصص المسجلة في هذه المجموعة
        sessions_count = Attendance.objects.filter(
            student=student,
            session__group=group,
            session__session_date__gte=current_month
        ).count()

        # تحديث أو إنشاء سجل الدفع
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
            payment.save()
