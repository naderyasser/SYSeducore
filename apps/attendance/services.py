from datetime import datetime, timedelta
from django.utils import timezone
from .models import Attendance, Session
from apps.students.models import Student
from apps.payments.models import Payment


class AttendanceService:
    
    @staticmethod
    def process_scan(barcode, supervisor):
        """
        معالجة مسح الباركود مع الفحص الثلاثي
        النظام يدعم الآن انتساب الطالب لأكثر من مجموعة
        """
        try:
            # 1. البحث عن الطالب
            student = Student.objects.prefetch_related('groups').get(
                barcode=barcode,
                is_active=True
            )
        except Student.DoesNotExist:
            return {
                'success': False,
                'message': 'كارنيه غير صالح',
                'sound': 'error'
            }

        # 2. البحث عن المجموعة المناسبة بناءً على الوقت واليوم
        current_time = timezone.now()
        current_day = current_time.weekday()

        # جلب كل المجموعات المسجل فيها الطالب
        from apps.students.models import StudentGroupEnrollment
        enrollments = StudentGroupEnrollment.objects.filter(
            student=student,
            is_active=True
        ).select_related('group')

        matching_group = None
        enrollment = None

        for enr in enrollments:
            group = enr.group
            # فحص اليوم
            day_check = AttendanceService.check_day(group.schedule_day)
            if not day_check['allowed']:
                continue

            # فحص الوقت
            time_check = AttendanceService.check_time(
                current_time,
                group.schedule_time,
                group.grace_period
            )
            if time_check['allowed']:
                matching_group = group
                enrollment = enr
                break

        if not matching_group:
            return {
                'success': False,
                'message': 'لا توجد حصة مناسبة الآن لهذا الطالب',
                'sound': 'error'
            }

        # 3. الحصول على أو إنشاء الحصة
        session, created = Session.objects.get_or_create(
            group=matching_group,
            session_date=timezone.now().date(),
            defaults={'teacher_attended': False}
        )

        # 4. التحقق من عدم التسجيل المسبق
        if Attendance.objects.filter(student=student, session=session).exists():
            return {
                'success': False,
                'message': 'تم تسجيل الحضور مسبقاً',
                'sound': 'error'
            }

        # 5. Triple Check - فحص الوقت مرة أخرى بالتفصيل
        time_check = AttendanceService.check_time(
            current_time,
            matching_group.schedule_time,
            matching_group.grace_period
        )

        if not time_check['allowed']:
            return {
                'success': False,
                'message': time_check['reason'],
                'sound': 'error'
            }

        # 6. فحص الحالة المالية للمجموعة المحددة
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

        # 7. تسجيل الحضور
        attendance = Attendance.objects.create(
            student=student,
            session=session,
            scan_time=timezone.now(),
            status=time_check['status'],
            supervisor=supervisor
        )

        # 8. تحديث عدد الحصص في Payment
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
    def check_time(scan_time, schedule_time, grace_period):
        """
        Check 1: فحص الوقت
        """
        # تحويل schedule_time إلى datetime
        today = timezone.now().date()
        session_start = timezone.make_aware(
            datetime.combine(today, schedule_time)
        )
        
        diff = scan_time - session_start
        diff_minutes = diff.total_seconds() / 60
        
        # السماح بالوصول قبل 30 دقيقة
        if diff_minutes < -30:
            return {
                'allowed': False,
                'reason': 'وصلت مبكراً جداً'
            }
        
        # فحص وقت السماح
        if diff_minutes > grace_period:
            return {
                'allowed': False,
                'reason': f'انتهى وقت السماح (تأخرت {int(diff_minutes)} دقيقة)'
            }
        
        return {
            'allowed': True,
            'status': 'late' if diff_minutes > 0 else 'present',
            'minutes_late': max(0, int(diff_minutes))
        }
    
    @staticmethod
    def check_day(schedule_day):
        """
        Check 2: فحص اليوم
        """
        days_map = {
            'Saturday': 5,
            'Sunday': 6,
            'Monday': 0,
            'Tuesday': 1,
            'Wednesday': 2,
            'Thursday': 3,
            'Friday': 4,
        }
        
        today = timezone.now().weekday()
        expected_day = days_map.get(schedule_day)
        
        if today != expected_day:
            return {
                'allowed': False,
                'reason': f'ليس موعد مجموعتك (موعدك يوم {schedule_day})'
            }
        
        return {'allowed': True}
    
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
        Check 3: فحص الحالة المالية
        يتحقق من الحالة المالية للطالب في المجموعة المحددة
        """
        from apps.students.models import StudentGroupEnrollment

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
