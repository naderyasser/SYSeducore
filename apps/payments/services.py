from django.db.models import Sum, Q
from django.db import transaction, models
from django.utils import timezone
from datetime import datetime
from .models import Payment, PaymentAuditLog
from apps.teachers.models import Group
from apps.students.models import StudentGroupEnrollment
from apps.attendance.models import Attendance
from apps.notifications.services import WhatsAppService
from apps.notifications.tasks import send_payment_confirmation_task
from .whatsapp_templates import get_credit_whatsapp_message


class CreditService:
    """
    خدمة إدارة نظام الائتمان للطلاب
    Credit System Service for managing student credits
    
    القواعد:
    - الطلاب الجدد: credit_balance = 0 (يجب الدفع قبل أول حصة)
    - الطلاب القدامى: credit_balance = 2 (فترة سماح لحصتين)
    """

    # ثوابت النظام
    NEW_STUDENT_CREDIT = 0
    RETURNING_STUDENT_CREDIT = 2
    CREDIT_LIMIT_WARNING = 1  # إرسال تحذير عند حصة واحدة متبقية

    @staticmethod
    @transaction.atomic
    def check_credit_status(student, group):
        """
        فحص حالة الائتمان للطالب في مجموعة معينة
        
        Args:
            student: كائن الطالب
            group: كائن المجموعة
            
        Returns:
            dict: {
                'allowed': bool,
                'reason': str,
                'message': str,
                'credit_info': dict
            }
        """
        try:
            enrollment = StudentGroupEnrollment.objects.select_for_update().get(
                student=student,
                group=group,
                is_active=True
            )
            
            # الحصول على حالة الائتمان
            credit_info = enrollment.get_credit_status()
            
            # التحقق من إمكانية الحضور
            can_attend = enrollment.can_attend_session()
            
            return {
                'allowed': can_attend['allowed'],
                'reason': can_attend['reason'],
                'message': can_attend['message'],
                'credit_info': credit_info
            }
            
        except StudentGroupEnrollment.DoesNotExist:
            return {
                'allowed': False,
                'reason': 'not_enrolled',
                'message': '⛔ غير مسجل في هذه المجموعة',
                'credit_info': None
            }

    @staticmethod
    @transaction.atomic
    def calculate_debt(student, group):
        """
        حساب ديون الطالب (عدد الحصص غير المدفوعة)
        
        Args:
            student: كائن الطالب
            group: كائن المجموعة
            
        Returns:
            int: عدد الحصص غير المدفوعة
        """
        try:
            enrollment = StudentGroupEnrollment.objects.get(
                student=student,
                group=group,
                is_active=True
            )
            
            debt = enrollment.sessions_attended - enrollment.sessions_paid_for
            return max(0, debt)
            
        except StudentGroupEnrollment.DoesNotExist:
            return 0

    @staticmethod
    @transaction.atomic
    def auto_block_if_exceeded(student, group):
        """
        التحقق التلقائي من تجاوز الحد المسموح وحظر الطالب
        
        Args:
            student: كائن الطالب
            group: كائن المجموعة
            
        Returns:
            dict: {
                'blocked': bool,
                'reason': str,
                'message': str
            }
        """
        try:
            enrollment = StudentGroupEnrollment.objects.select_for_update().get(
                student=student,
                group=group,
                is_active=True
            )
            
            # الإعفاء الكامل لا يتم حظره
            if enrollment.financial_status == 'exempt':
                return {
                    'blocked': False,
                    'reason': 'exempt',
                    'message': ''
                }
            
            # حساب الدين
            debt = enrollment.sessions_attended - enrollment.sessions_paid_for
            remaining_credit = enrollment.credit_balance - debt
            
            # طالب جديد بدون دفع
            if enrollment.is_new_student and enrollment.sessions_paid_for == 0:
                enrollment.is_financially_blocked = True
                enrollment.financial_block_reason = 'new_student_no_payment'
                enrollment.save()
                
                # تسجيل في سجل التدقيق
                CreditService._log_audit(
                    student=student,
                    group=group,
                    action='block_applied',
                    notes='طالب جديد بدون دفع'
                )
                
                return {
                    'blocked': True,
                    'reason': 'new_student_no_payment',
                    'message': '⛔ ممنوع الدخول - يرجى تسجيل المصروفات أولاً'
                }
            
            # تجاوز حد الائتمان
            if remaining_credit < 0:
                enrollment.is_financially_blocked = True
                enrollment.financial_block_reason = f'credit_exceeded_{abs(remaining_credit)}'
                enrollment.save()
                
                # تسجيل في سجل التدقيق
                CreditService._log_audit(
                    student=student,
                    group=group,
                    action='block_applied',
                    notes=f'تجاوز حد الائتمان: {debt} حصة غير مدفوعة'
                )
                
                return {
                    'blocked': True,
                    'reason': 'credit_exceeded',
                    'message': f'⛔ ممنوع الدخول - لديك {debt} حصة غير مدفوعة'
                }
            
            # إزالة الحظر إذا تم الدفع
            if enrollment.is_financially_blocked and remaining_credit >= 0:
                enrollment.is_financially_blocked = False
                enrollment.financial_block_reason = ''
                enrollment.save()
                
                # تسجيل في سجل التدقيق
                CreditService._log_audit(
                    student=student,
                    group=group,
                    action='block_removed',
                    notes='تم إزالة الحظر المالي'
                )
            
            return {
                'blocked': False,
                'reason': 'ok',
                'message': ''
            }
            
        except StudentGroupEnrollment.DoesNotExist:
            return {
                'blocked': True,
                'reason': 'not_enrolled',
                'message': '⛔ غير مسجل في هذه المجموعة'
            }

    @staticmethod
    @transaction.atomic
    def record_payment_and_update_credit(student, group, amount, sessions_count, performed_by=None, notes=''):
        """
        تسجيل دفع وتحديث ائتمان الطالب
        
        Args:
            student: كائن الطالب
            group: كائن المجموعة
            amount: المبلغ المدفوع
            sessions_count: عدد الحصص المدفوعة
            performed_by: المستخدم الذي قام بالتسجيل
            notes: ملاحظات إضافية
            
        Returns:
            dict: {
                'success': bool,
                'message': str,
                'enrollment': StudentGroupEnrollment
            }
        """
        try:
            enrollment = StudentGroupEnrollment.objects.select_for_update().get(
                student=student,
                group=group,
                is_active=True
            )
            
            # حفظ القيم القديمة للسجل
            old_values = {
                'sessions_paid_for': enrollment.sessions_paid_for,
                'credit_balance': enrollment.credit_balance,
                'last_payment_amount': float(enrollment.last_payment_amount) if enrollment.last_payment_amount else 0,
            }
            
            # تحديث عدد الحصص المدفوعة
            enrollment.sessions_paid_for += sessions_count
            enrollment.last_payment_date = timezone.now()
            enrollment.last_payment_amount = amount
            
            # إذا كان طالب جديد، قم بتحويله لطالب قديم بعد أول دفع
            if enrollment.is_new_student:
                enrollment.is_new_student = False
                enrollment.credit_balance = CreditService.RETURNING_STUDENT_CREDIT
            
            # إزالة الحظر المالي إذا كان موجوداً
            if enrollment.is_financially_blocked:
                enrollment.is_financially_blocked = False
                enrollment.financial_block_reason = ''
            
            enrollment.save()
            
            # حفظ القيم الجديدة
            new_values = {
                'sessions_paid_for': enrollment.sessions_paid_for,
                'credit_balance': enrollment.credit_balance,
                'last_payment_amount': float(enrollment.last_payment_amount),
            }
            
            # تسجيل في سجل التدقيق
            CreditService._log_audit(
                student=student,
                group=group,
                action='payment_recorded',
                old_value=old_values,
                new_value=new_values,
                amount=amount,
                sessions_count=sessions_count,
                notes=notes,
                performed_by=performed_by
            )
            
            # تحديث أو إنشاء سجل الدفع الشهري
            current_month = timezone.now().replace(day=1)
            payment, created = Payment.objects.get_or_create(
                student=student,
                group=group,
                month=current_month,
                defaults={
                    'amount_due': enrollment.get_effective_fee(),
                    'amount_paid': amount,
                    'payment_date': timezone.now(),
                    'status': 'paid' if amount >= enrollment.get_effective_fee() else 'partial'
                }
            )
            
            if not created:
                payment.amount_paid += amount
                payment.payment_date = timezone.now()
                if payment.amount_paid >= payment.amount_due:
                    payment.status = 'paid'
                else:
                    payment.status = 'partial'
                payment.save()
            
            # إرسال إشعار تأكيد استلام الدفع (Async)
            CreditService._trigger_payment_confirmation(
                student=student,
                amount=amount,
                payment=payment
            )
            
            return {
                'success': True,
                'message': f'تم تسجيل الدفع بنجاح: {sessions_count} حصة',
                'enrollment': enrollment
            }
            
        except StudentGroupEnrollment.DoesNotExist:
            return {
                'success': False,
                'message': 'الطالب غير مسجل في هذه المجموعة'
            }

    @staticmethod
    @transaction.atomic
    def record_attendance_and_update_credit(student, group):
        """
        تسجيل الحضور وتحديث عداد الحصص المحضور
        يتم استدعاؤه بعد تسجيل الحضور بنجاح
        
        Args:
            student: كائن الطالب
            group: كائن المجموعة
        """
        try:
            enrollment = StudentGroupEnrollment.objects.select_for_update().get(
                student=student,
                group=group,
                is_active=True
            )
            
            enrollment.sessions_attended += 1
            enrollment.save()
            
            # التحقق من الحاجة لإرسال تحذير
            debt = enrollment.sessions_attended - enrollment.sessions_paid_for
            remaining_credit = enrollment.credit_balance - debt
            
            # إرسال تحذير عند حصة واحدة متبقية
            if remaining_credit == CreditService.CREDIT_LIMIT_WARNING:
                CreditService._send_credit_warning(student, group, remaining_credit)
            
            # إرسال تحذير عند الحصة الثانية غير المدفوعة
            if debt == 2 and not enrollment.is_new_student:
                CreditService._send_final_warning(student, group)
            
        except StudentGroupEnrollment.DoesNotExist:
            pass

    @staticmethod
    @transaction.atomic
    def adjust_credit_balance(student, group, new_balance, performed_by=None, notes=''):
        """
        تعديل رصيد الائتمان يدوياً (للإدارة فقط)
        
        Args:
            student: كائن الطالب
            group: كائن المجموعة
            new_balance: الرصيد الجديد
            performed_by: المستخدم الذي قام بالتعديل
            notes: ملاحظات إضافية
        """
        try:
            enrollment = StudentGroupEnrollment.objects.select_for_update().get(
                student=student,
                group=group,
                is_active=True
            )
            
            old_balance = enrollment.credit_balance
            enrollment.credit_balance = new_balance
            enrollment.save()
            
            # تسجيل في سجل التدقيق
            CreditService._log_audit(
                student=student,
                group=group,
                action='credit_adjustment',
                old_value={'credit_balance': old_balance},
                new_value={'credit_balance': new_balance},
                notes=notes,
                performed_by=performed_by
            )
            
            return {
                'success': True,
                'message': f'تم تعديل رصيد الائتمان من {old_balance} إلى {new_balance}'
            }
            
        except StudentGroupEnrollment.DoesNotExist:
            return {
                'success': False,
                'message': 'الطالب غير مسجل في هذه المجموعة'
            }

    @staticmethod
    def _log_audit(student, group, action, old_value=None, new_value=None,
                   amount=None, sessions_count=None, notes='', performed_by=None):
        """تسجيل في سجل التدقيق المالي"""
        PaymentAuditLog.objects.create(
            student=student,
            group=group,
            action=action,
            old_value=old_value,
            new_value=new_value,
            amount=amount,
            sessions_count=sessions_count,
            notes=notes,
            performed_by=performed_by
        )

    @staticmethod
    def _send_credit_warning(student, group, remaining_credit):
        """إرسال تحذير عند اقتراب نفاد الائتمان"""
        context = {
            'student_name': student.full_name,
            'group_name': group.group_name,
            'remaining_credit': remaining_credit
        }
        
        notification = get_credit_whatsapp_message('credit_warning', context)
        
        try:
            whatsapp = WhatsAppService()
            whatsapp.send_message(
                to=student.parent_phone,
                message=notification['message'],
                student=student,
                student_name=student.full_name,
                notification_type='credit_warning'
            )
        except Exception as e:
            print(f"Failed to send credit warning: {e}")

    @staticmethod
    def _send_final_warning(student, group):
        """إرسال تحذير نهائي عند الحصة الثانية غير المدفوعة"""
        context = {
            'student_name': student.full_name,
            'group_name': group.group_name
        }
        
        notification = get_credit_whatsapp_message('credit_final_warning', context)
        
        try:
            whatsapp = WhatsAppService()
            whatsapp.send_message(
                to=student.parent_phone,
                message=notification['message'],
                student=student,
                student_name=student.full_name,
                notification_type='credit_final_warning'
            )
        except Exception as e:
            print(f"Failed to send final warning: {e}")

    @staticmethod
    def _trigger_payment_confirmation(student, amount, payment):
        """
        Trigger async notification for payment confirmation
        
        Payment Received Confirmation:
        Trigger: When payment is recorded in system
        """
        try:
            # Generate receipt number
            receipt_number = f"PAY-{payment.payment_date.strftime('%Y%m%d')}-{payment.payment_id}"
            
            send_payment_confirmation_task.delay(
                student_id=student.student_id,
                amount=float(amount),
                receipt_number=receipt_number,
                payment_date_str=payment.payment_date.isoformat()
            )
        except Exception as e:
            # Don't block payment if notification task fails
            print(f"Failed to queue payment confirmation notification: {e}")

    @staticmethod
    def get_students_with_debt(group=None):
        """
        الحصول على قائمة الطلاب الذين لديهم ديون
        
        Args:
            group: تصفية حسب المجموعة (اختياري)
            
        Returns:
            QuerySet: تسجيلات الطلاب الذين لديهم ديون
        """
        enrollments = StudentGroupEnrollment.objects.filter(
            is_active=True
        ).annotate(
            debt=models.F('sessions_attended') - models.F('sessions_paid_for')
        ).filter(
            debt__gt=0
        ).select_related('student', 'group')
        
        if group:
            enrollments = enrollments.filter(group=group)
        
        return enrollments

    @staticmethod
    def get_credit_report(group=None, student=None):
        """
        الحصول على تقرير شامل عن حالة الائتمان
        
        Args:
            group: تصفية حسب المجموعة (اختياري)
            student: تصفية حسب الطالب (اختياري)
            
        Returns:
            dict: تقرير شامل
        """
        enrollments = StudentGroupEnrollment.objects.filter(is_active=True)
        
        if group:
            enrollments = enrollments.filter(group=group)
        if student:
            enrollments = enrollments.filter(student=student)
        
        enrollments = enrollments.select_related('student', 'group')
        
        report = {
            'total_enrollments': enrollments.count(),
            'new_students': enrollments.filter(is_new_student=True).count(),
            'returning_students': enrollments.filter(is_new_student=False).count(),
            'financially_blocked': enrollments.filter(is_financially_blocked=True).count(),
            'with_debt': 0,
            'details': []
        }
        
        for enrollment in enrollments:
            debt = enrollment.sessions_attended - enrollment.sessions_paid_for
            if debt > 0:
                report['with_debt'] += 1
            
            report['details'].append({
                'student_name': enrollment.student.full_name,
                'group_name': enrollment.group.group_name,
                'is_new_student': enrollment.is_new_student,
                'credit_balance': enrollment.credit_balance,
                'sessions_attended': enrollment.sessions_attended,
                'sessions_paid_for': enrollment.sessions_paid_for,
                'debt': debt,
                'is_blocked': enrollment.is_financially_blocked,
                'block_reason': enrollment.financial_block_reason,
            })
        
        return report


class SettlementService:
    
    @staticmethod
    def calculate_teacher_settlement(teacher_id, year, month):
        """
        حساب مستحقات المدرس لشهر معين
        """
        # الحصول على مجموعات المدرس
        groups = Group.objects.filter(teacher_id=teacher_id)
        
        total_revenue = 0
        breakdown = []
        
        for group in groups:
            group_data = SettlementService.calculate_group_revenue(
                group.group_id, year, month
            )
            
            total_revenue += group_data['revenue']
            breakdown.append({
                'group_name': group.group_name,
                'students': group_data['students'],
                'revenue': group_data['revenue']
            })
        
        # حساب الحصص
        center_percentage = groups.first().center_percentage if groups.exists() else 30
        center_share = total_revenue * (center_percentage / 100)
        teacher_share = total_revenue - center_share
        
        return {
            'success': True,
            'data': {
                'teacher_id': teacher_id,
                'year': year,
                'month': month,
                'total_revenue': round(float(total_revenue), 2),
                'center_share': round(float(center_share), 2),
                'teacher_share': round(float(teacher_share), 2),
                'center_percentage': float(center_percentage),
                'breakdown': breakdown
            }
        }
    
    @staticmethod
    def calculate_group_revenue(group_id, year, month):
        """
        حساب إيرادات مجموعة معينة
        الآن يدعم الطلاب المسجلين في مجموعات متعددة
        """
        from apps.teachers.models import Group
        from apps.students.models import StudentGroupEnrollment

        start_date = datetime(year, month, 1).date()

        # آخر يوم في الشهر
        if month == 12:
            end_date = datetime(year + 1, 1, 1).date()
        else:
            end_date = datetime(year, month + 1, 1).date()

        # الحصول على المدفوعات لهذه المجموعة
        payments = Payment.objects.filter(
            group_id=group_id,
            month__gte=start_date,
            month__lt=end_date
        ).select_related('student', 'group')

        revenue = 0
        students = []

        for payment in payments:
            student = payment.student
            group = payment.group

            # جلب الحالة المالية من التسجيل
            try:
                enrollment = StudentGroupEnrollment.objects.get(
                    student=student,
                    group=group
                )
                financial_status_display = enrollment.get_financial_status_display()
            except StudentGroupEnrollment.DoesNotExist:
                financial_status_display = 'غير محدد'

            expected_fee = student.get_monthly_fee_for_group(group)
            amount_paid = float(payment.amount_paid)

            revenue += amount_paid

            students.append({
                'name': student.full_name,
                'financial_status': financial_status_display,
                'expected_fee': float(expected_fee),
                'amount_paid': amount_paid,
                'payment_status': payment.get_status_display(),
                'sessions_attended': payment.sessions_attended
            })

        return {
            'revenue': revenue,
            'students': students
        }
