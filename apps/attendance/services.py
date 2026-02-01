"""
Attendance Service - STRICT MODE
No tolerance for late arrivals - 1 minute late = BLOCKED
"""
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction
from .models import Attendance, Session, BlockedAttempt
from apps.students.models import Student, StudentGroupEnrollment
from apps.payments.models import Payment
from apps.payments.services import CreditService
from apps.payments.whatsapp_templates import get_credit_whatsapp_message
from apps.notifications.tasks import (
    send_attendance_success_task,
    send_late_block_task,
    send_financial_block_new_task,
    send_financial_block_debt_task,
)


class AttendanceService:
    """
    خدمة تسجيل الحضور - النظام الصارم (STRICT MODE)
    
    القواعد الجديدة:
    - 🟢 GREEN (Present): -30 إلى 0 دقيقة = مسموح
    - 🔴 RED (Late Blocked): 1-10 دقائق تأخير = ممنوع
    - 🔴 RED (Very Late): 10+ دقائق تأخير = ممنوع
    - ⚪ WHITE (No Session): لا توجد حصة = ممنوع
    - 🟡 YELLOW (Payment): مشكلة مالية = ممنوع
    """

    # ثوابت النظام الصارم
    EARLY_ARRIVAL_LIMIT_MINUTES = 30  # السماح بالوصول قبل 30 دقيقة
    LATE_BLOCK_THRESHOLD_MINUTES = 0  # 0 دقيقة = صارم جداً (أي تأخير = ممنوع)
    VERY_LATE_THRESHOLD_MINUTES = 10  # 10+ دقائق = تأخير شديد

    @staticmethod
    @transaction.atomic
    def process_scan(student_code, supervisor):
        """
        معالجة إدخال كود الطالب - النظام الصارم
        
        الخوارزمية (4 خطوات):
        1. جلب الطالب بـ student_code
        2. مطابقة الجدول (الوقت واليوم الحاليين)
        3. فحص الوقت الصارم (أي تأخير = ممنوع)
        4. فحص مالي
        
        الإرجاع:
        - success: True/False
        - status: present, late_blocked, very_late, no_session, blocked_payment, blocked_other
        - color_code: green, red, yellow, white, gray
        - allow_entry: True/False
        - message: رسالة للعرض
        - student_name: اسم الطالب
        - minutes_late: دقائق التأخير
        """
        current_time = timezone.now()
        
        # ========================================
        # الخطوة 1: التعريف - جلب الطالب
        # ========================================
        try:
            student = Student.objects.prefetch_related('groups').get(
                student_code=student_code,
                is_active=True
            )
        except Student.DoesNotExist:
            return AttendanceService._create_blocked_response(
                student=None,
                status='blocked_other',
                color_code='white',
                allow_entry=False,
                message='كود غير صالح',
                minutes_late=0,
                reason='invalid_code',
                current_time=current_time
            )

        # ========================================
        # الخطوة 2: مطابقة الجدول
        # ========================================
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
            # لا توجد حصة مجدولة
            return AttendanceService._create_blocked_response(
                student=student,
                status='no_session',
                color_code='white',
                allow_entry=False,
                message='لا توجد حصة مجدولة لك اليوم',
                minutes_late=0,
                reason='no_session',
                current_time=current_time
            )

        # ========================================
        # الخطوة 2.5: فحص إلغاء الحصة (CRITICAL CHECK)
        # ========================================
        # Get or create session for today
        session, _ = Session.objects.get_or_create(
            group=matching_group,
            session_date=current_time.date()
        )
        
        # Check if session is cancelled
        if session.is_cancelled:
            return AttendanceService._create_blocked_response(
                student=student,
                status='no_session',
                color_code='white',
                allow_entry=False,
                message=f'تم إلغاء الحصة اليوم\n{session.cancellation_reason}',
                minutes_late=0,
                reason='session_cancelled',
                current_time=current_time,
                group_name=matching_group.group_name
            )

        # ========================================
        # الخطوة 3: فحص الوقت الصارم (STRICT MODE)
        # ========================================
        time_check = AttendanceService._check_strict_time(
            current_time,
            matching_group.schedule_time
        )

        if not time_check['allowed']:
            # تسجيل محاولة الدخول الممنوعة
            AttendanceService._create_blocked_attempt(
                student=student,
                group=matching_group,
                reason=time_check['reason_code'],
                minutes_late=time_check['minutes_late'],
                current_time=current_time
            )
            
            # إرسال إخطار WhatsApp لولي الأمر (Async - لا يمنع عملية المسح)
            AttendanceService._trigger_late_block_notification(
                student=student,
                group=matching_group,
                time_check=time_check,
                current_time=current_time
            )
            
            return AttendanceService._create_blocked_response(
                student=student,
                status=time_check['status'],
                color_code='red',
                allow_entry=False,
                message=time_check['message'],
                minutes_late=time_check['minutes_late'],
                reason=time_check['reason_code'],
                current_time=current_time,
                group_name=matching_group.group_name
            )

        # ========================================
        # الخطوة 4: الفحص المالي
        # ========================================
        financial_check = AttendanceService._check_financial_status(
            student,
            matching_group
        )

        if not financial_check['allowed']:
            # تسجيل محاولة الدخول الممنوعة (مالية)
            AttendanceService._create_blocked_attempt(
                student=student,
                group=matching_group,
                reason='payment',
                minutes_late=time_check['minutes_late'],
                current_time=current_time
            )
            
            # إرسال إخطار WhatsApp للحظر المالي (Async)
            AttendanceService._trigger_financial_block_notification(
                student=student,
                group=matching_group,
                financial_check=financial_check
            )
            
            return AttendanceService._create_blocked_response(
                student=student,
                status='blocked_payment',
                color_code='yellow',
                allow_entry=False,
                message=financial_check['message'],
                minutes_late=time_check['minutes_late'],
                reason='payment',
                current_time=current_time,
                group_name=matching_group.group_name
            )

        # ========================================
        # التسجيل النهائي (حضور مسموح)
        # ========================================
        # Session already retrieved in step 2.5, no need to get_or_create again

        # التحقق من عدم التسجيل المسبق
        if Attendance.objects.filter(student=student, session=session).exists():
            return {
                'success': False,
                'status': 'blocked_other',
                'color_code': 'gray',
                'allow_entry': False,
                'message': 'تم تسجيل الحضور مسبقاً',
                'student_name': student.full_name,
                'minutes_late': time_check['minutes_late']
            }

        # تسجيل الحضور
        attendance = Attendance.objects.create(
            student=student,
            session=session,
            scan_time=current_time,
            status='present',
            color_code='green',
            allow_entry=True,
            minutes_late=time_check['minutes_late'],
            supervisor=supervisor
        )

        # تحديث عدد الحصص في Payment
        AttendanceService.update_payment_sessions(student, matching_group)

        # إرسال إشعار الحضور الناجح (Async - لا يمنع عملية المسح)
        AttendanceService._trigger_attendance_success_notification(
            student=student,
            group=matching_group,
            scan_time=current_time
        )

        return {
            'success': True,
            'status': 'present',
            'color_code': 'green',
            'allow_entry': True,
            'message': f'مرحباً {student.full_name} - {matching_group.group_name}',
            'student_name': student.full_name,
            'minutes_late': time_check['minutes_late'],
            'time': current_time.strftime('%H:%M:%S'),
            'student': student,
            'group': matching_group,
            'attendance': attendance
        }

    @staticmethod
    def _check_strict_time(scan_time, schedule_time):
        """
        فحص الوقت الصارم - STRICT MODE
        
        القواعد:
        - 🟢 GREEN: -30 إلى 0 دقيقة (في الموعد أو مبكر) = مسموح
        - 🔴 RED: 1-10 دقائق تأخير = ممنوع
        - 🔴 RED: 10+ دقائق تأخير = ممنوع (تأخير شديد)
        
        Args:
            scan_time: وقت المسح
            schedule_time: الوقت المجدول للحصة
            
        Returns:
            dict: {
                'allowed': bool,
                'status': str,
                'message': str,
                'minutes_late': int,
                'reason_code': str
            }
        """
        # تحويل schedule_time إلى datetime
        today = timezone.now().date()
        session_start = timezone.make_aware(
            datetime.combine(today, schedule_time)
        )

        # حساب الفرق بالدقائق
        diff = scan_time - session_start
        diff_minutes = int(diff.total_seconds() / 60)

        # الحالة 1: وصول مبكر جداً (أكثر من 30 دقيقة قبل الموعد)
        if diff_minutes < -AttendanceService.EARLY_ARRIVAL_LIMIT_MINUTES:
            return {
                'allowed': False,
                'status': 'blocked_other',
                'message': f'وصلت مبكراً جداً. الموعد: {schedule_time.strftime("%I:%M %p")}',
                'minutes_late': diff_minutes,
                'reason_code': 'too_early'
            }

        # الحالة 2: في الموعد أو مبكر (من -30 إلى 0 دقيقة) = مسموح 🟢
        if diff_minutes <= AttendanceService.LATE_BLOCK_THRESHOLD_MINUTES:
            return {
                'allowed': True,
                'status': 'present',
                'message': 'حضور مسجل',
                'minutes_late': diff_minutes,
                'reason_code': 'on_time'
            }

        # الحالة 3: تأخير (1-10 دقائق) = ممنوع 🔴
        if diff_minutes <= AttendanceService.VERY_LATE_THRESHOLD_MINUTES:
            return {
                'allowed': False,
                'status': 'late_blocked',
                'message': f'⛔ ممنوع الدخول - تأخرت {diff_minutes} دقيقة',
                'minutes_late': diff_minutes,
                'reason_code': 'late'
            }

        # الحالة 4: تأخير شديد (10+ دقائق) = ممنوع 🔴
        return {
            'allowed': False,
            'status': 'very_late',
            'message': f'⛔ ممنوع الدخول - تأخير شديد ({diff_minutes} دقيقة)',
            'minutes_late': diff_minutes,
            'reason_code': 'very_late'
        }

    @staticmethod
    def _check_financial_status(student, group):
        """
        فحص الحالة المالية للطالب باستخدام نظام الائتمان الجديد
        
        القواعد:
        - الطلاب الجدد: يجب الدفع قبل أول حصة
        - الطلاب القدامى: يمكنهم حضور حصتين بدون دفع
        - الحصة الثالثة بدون دفع = حظر تلقائي
        
        Returns:
            dict: {'allowed': bool, 'message': str}
        """
        # استخدام CreditService للفحص
        credit_check = CreditService.check_credit_status(student, group)
        
        if not credit_check['allowed']:
            # إرسال إخطار WhatsApp للحظر المالي
            AttendanceService._send_financial_block_notification(
                student, group, credit_check['reason']
            )
        
        return {
            'allowed': credit_check['allowed'],
            'message': credit_check['message']
        }

    @staticmethod
    def _create_blocked_response(student, status, color_code, allow_entry, 
                                 message, minutes_late, reason, current_time, 
                                 group_name=''):
        """
        إنشاء استجابة منع موحدة
        """
        return {
            'success': False,
            'status': status,
            'color_code': color_code,
            'allow_entry': allow_entry,
            'message': message,
            'student_name': student.full_name if student else 'غير معروف',
            'minutes_late': minutes_late,
            'reason': reason,
            'time': current_time.strftime('%H:%M:%S'),
            'group_name': group_name
        }

    @staticmethod
    def _create_blocked_attempt(student, group, reason, minutes_late, current_time):
        """
        تسجيل محاولة دخول ممنوعة في سجل التدقيق
        """
        BlockedAttempt.objects.create(
            student=student,
            session=None,  # Will be linked if session exists
            attempt_time=current_time,
            reason=reason,
            minutes_late=minutes_late,
            group_name=group.group_name,
            scheduled_time=group.schedule_time
        )

    @staticmethod
    def _trigger_attendance_success_notification(student, group, scan_time):
        """
        Trigger async notification for successful attendance
        
        🟢 SUCCESSFUL ATTENDANCE:
        Trigger: Student scans QR, status = present, allow_entry = true
        """
        try:
            send_attendance_success_task.delay(
                student_id=student.student_id,
                group_id=group.group_id,
                scan_time_str=scan_time.isoformat()
            )
        except Exception as e:
            # Don't block attendance if notification task fails
            print(f"Failed to queue attendance success notification: {e}")

    @staticmethod
    def _trigger_late_block_notification(student, group, time_check, current_time):
        """
        Trigger async notification for late block
        
        🔴 LATE BLOCK:
        Trigger: Student scans QR, status = late_blocked, allow_entry = false
        """
        try:
            scheduled_time_str = group.schedule_time.strftime('%H:%M')
            scan_time_str = current_time.strftime('%H:%M')
            
            send_late_block_task.delay(
                student_id=student.student_id,
                group_id=group.group_id,
                minutes_late=time_check['minutes_late'],
                scheduled_time=scheduled_time_str,
                scan_time=scan_time_str
            )
        except Exception as e:
            # Don't block attendance if notification task fails
            print(f"Failed to queue late block notification: {e}")

    @staticmethod
    def _trigger_financial_block_notification(student, group, financial_check):
        """
        Trigger async notification for financial block
        
        🟡 FINANCIAL BLOCK (New Student):
        Trigger: Student scans QR, is_new_student = true, no payment
        
        🟡 FINANCIAL BLOCK (Debt Exceeded):
        Trigger: Old student, debt > 2 sessions
        """
        try:
            reason = financial_check.get('reason', '')
            
            if reason == 'new_student_no_payment':
                # 🟡 FINANCIAL BLOCK (New Student)
                send_financial_block_new_task.delay(
                    student_id=student.student_id,
                    group_id=group.group_id
                )
            elif reason in ['credit_exceeded', 'debt_exceeded']:
                # 🟡 FINANCIAL BLOCK (Debt Exceeded)
                enrollment = StudentGroupEnrollment.objects.get(
                    student=student,
                    group=group
                )
                unpaid_sessions = enrollment.sessions_attended - enrollment.sessions_paid_for
                due_amount = enrollment.get_effective_fee() * unpaid_sessions
                
                send_financial_block_debt_task.delay(
                    student_id=student.student_id,
                    group_id=group.group_id,
                    unpaid_sessions=unpaid_sessions,
                    due_amount=due_amount
                )
        except Exception as e:
            # Don't block attendance if notification task fails
            print(f"Failed to queue financial block notification: {e}")

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
    def update_payment_sessions(student, group):
        """
        تحديث عدد الحصص في سجل المدفوعات ونظام الائتمان
        """
        # تحديث نظام الائتمان
        CreditService.record_attendance_and_update_credit(student, group)
        
        # تحديث سجل المدفوعات الشهري
        current_month = timezone.now().replace(day=1)
        payment = Payment.objects.filter(
            student=student,
            group=group,
            month=current_month
        ).first()
        
        if payment:
            payment.sessions_attended += 1
            payment.save()


class AttendanceReportService:
    """
    خدمة التقارير والحضور
    """
    
    @staticmethod
    def get_session_statistics(session_id):
        """
        الحصول على إحصائيات الحصة
        """
        session = Session.objects.get(pk=session_id)
        attendances = session.attendances.all()
        
        return {
            'total': attendances.count(),
            'present': attendances.filter(status='present', allow_entry=True).count(),
            'blocked': attendances.filter(allow_entry=False).count(),
            'late_blocked': attendances.filter(status='late_blocked').count(),
            'very_late': attendances.filter(status='very_late').count(),
            'payment_blocked': attendances.filter(status='blocked_payment').count(),
            'no_session': attendances.filter(status='no_session').count(),
        }
    
    @staticmethod
    def get_blocked_attempts_report(student_id=None, start_date=None, end_date=None):
        """
        تقرير محاولات الدخول الممنوعة
        """
        attempts = BlockedAttempt.objects.all()
        
        if student_id:
            attempts = attempts.filter(student_id=student_id)
        if start_date:
            attempts = attempts.filter(attempt_time__gte=start_date)
        if end_date:
            attempts = attempts.filter(attempt_time__lte=end_date)
            
        return attempts.select_related('student', 'session')
