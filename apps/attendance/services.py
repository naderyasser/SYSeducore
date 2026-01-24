from datetime import datetime, timedelta
from django.utils import timezone
from .models import Attendance, Session
from apps.students.models import Student, StudentGroupEnrollment
from apps.payments.models import Payment


class AttendanceService:
    """
    خدمة تسجيل الحضور - النظام الثابت
    الخوارزمية: 4 خطوات صارمة بدون تعقيدات
    """

    # ثوابت النظام
    STRICT_GRACE_PERIOD_MINUTES = 10  # قاعدة الـ 10 دقائق الصارمة
    EARLY_ARRIVAL_LIMIT_MINUTES = 30  # السماح بالوصول قبل 30 دقيقة

    @staticmethod
    def process_scan(student_code, supervisor):
        """
        معالجة إدخال كود الطالب - النظام المبسط

        الخوارزمية (4 خطوات):
        1. جلب الطالب بـ student_code
        2. مطابقة الجدول (الوقت واليوم الحاليين)
        3. قاعدة 10 دقائق صارمة (>10 = BLOCK)
        4. فحص مالي
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
        # الخطوة 2: مطابقة الجدول
        # ========================================
        current_time = timezone.now()
        current_day_name = AttendanceService.get_current_day_name()

        # جلب كل المجموعات المسجل فيها الطالب
        enrollments = StudentGroupEnrollment.objects.filter(
            student=student,
            is_active=True
        ).select_related('group')

        matching_group = None
        enrollment = None

        # البحث عن المجموعة التي موعدها الآن (نفس اليوم فقط)
        for enr in enrollments:
            group = enr.group

            # مطابقة اليوم
            if group.schedule_day != current_day_name:
                continue

            # هذه هي المجموعة المطابقة لليوم
            matching_group = group
            enrollment = enr
            break

        if not matching_group:
            return {
                'success': False,
                'message': 'لا توجد حصة مجدولة لك اليوم',
                'sound': 'error'
            }

        # ========================================
        # الخطوة 3: قاعدة الـ 10 دقائق الصارمة
        # ========================================
        time_check = AttendanceService.check_strict_time(
            current_time,
            matching_group.schedule_time
        )

        if not time_check['allowed']:
            return {
                'success': False,
                'message': time_check['reason'],
                'sound': 'error'
            }

        # ========================================
        # الخطوة 4: الفحص المالي
        # ========================================
        financial_check = AttendanceService.check_financial_status(
            student,
            matching_group
        )

        if not financial_check['allowed']:
            return {
                'success': False,
                'message': financial_check['reason'],
                'sound': 'error'
            }

        # ========================================
        # التسجيل النهائي
        # ========================================
        # الحصول على أو إنشاء الحصة
        session, _ = Session.objects.get_or_create(
            group=matching_group,
            session_date=timezone.now().date(),
            defaults={'teacher_attended': False}
        )

        # التحقق من عدم التسجيل المسبق
        if Attendance.objects.filter(student=student, session=session).exists():
            return {
                'success': False,
                'message': 'تم تسجيل الحضور مسبقاً',
                'sound': 'error'
            }

        # تسجيل الحضور
        attendance = Attendance.objects.create(
            student=student,
            session=session,
            scan_time=timezone.now(),
            status=time_check['status'],
            supervisor=supervisor
        )

        # تحديث عدد الحصص في Payment
        AttendanceService.update_payment_sessions(student, matching_group)

        return {
            'success': True,
            'message': f'مرحباً {student.full_name} - {matching_group.group_name}',
            'sound': 'success',
            'status': time_check['status'],
            'student': student,
            'group': matching_group,
            'attendance': attendance
        }
    
    @staticmethod
    def get_current_day_name():
        """
        الحصول على اسم اليوم الحالي بالإنجليزي
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
        return days_map.get(today)

    @staticmethod
    def check_strict_time(scan_time, schedule_time):
        """
        الخطوة 3: قاعدة الـ 10 دقائق الصارمة

        القواعد:
        - الوقت الفعلي مقارنة بالجدول الرسمي
        - ≤10 دقائق: قبول (حاضر)
        - >10 دقائق: رفض كامل (BLOCK)
        - لا يوجد "تأخير"، فقط قبول أو رفض
        """
        # تحويل schedule_time إلى datetime
        today = timezone.now().date()
        session_start = timezone.make_aware(
            datetime.combine(today, schedule_time)
        )

        # حساب الفرق بالدقائق
        diff = scan_time - session_start
        diff_minutes = diff.total_seconds() / 60

        # السماح بالوصول المبكر (30 دقيقة قبل الموعد)
        if diff_minutes < -AttendanceService.EARLY_ARRIVAL_LIMIT_MINUTES:
            return {
                'allowed': False,
                'reason': f'وصلت مبكراً جداً. الموعد: {schedule_time.strftime("%I:%M %p")}'
            }

        # القاعدة الصارمة: أكثر من 10 دقائق = رفض
        if diff_minutes > AttendanceService.STRICT_GRACE_PERIOD_MINUTES:
            return {
                'allowed': False,
                'reason': f'ممنوع الدخول - تأخرت {int(diff_minutes)} دقيقة (الحد المسموح: 10 دقائق)'
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
                'reason': 'الطالب غير مسجل في هذه المجموعة'
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

        # منع الدخول بعد الحصة المسموح إذا لم يدفع
        if sessions_count >= allowed_sessions:
            try:
                payment = Payment.objects.get(
                    student=student,
                    group=group,
                    month=current_month
                )
                if payment.status != 'paid':
                    if is_first_month:
                        return {
                            'allowed': False,
                            'reason': 'الشهر الأول: يجب الدفع أولاً قبل الدخول'
                        }
                    else:
                        return {
                            'allowed': False,
                            'reason': 'ممنوع الدخول - يرجى مراجعة الحسابات'
                        }
            except Payment.DoesNotExist:
                if is_first_month:
                    return {
                        'allowed': False,
                        'reason': 'الشهر الأول: يجب الدفع أولاً قبل الدخول'
                    }
                else:
                    return {
                        'allowed': False,
                        'reason': 'ممنوع الدخول - يرجى مراجعة الحسابات'
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
                'sessions_attended': sessions_count
            }
        )

        if not created:
            payment.sessions_attended = sessions_count
            payment.save()
