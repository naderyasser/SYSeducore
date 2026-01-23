from django.db.models import Sum, Q
from datetime import datetime
from .models import Payment
from apps.teachers.models import Group


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
        """
        start_date = datetime(year, month, 1).date()
        
        # آخر يوم في الشهر
        if month == 12:
            end_date = datetime(year + 1, 1, 1).date()
        else:
            end_date = datetime(year, month + 1, 1).date()
        
        # الحصول على المدفوعات
        payments = Payment.objects.filter(
            student__group_id=group_id,
            month__gte=start_date,
            month__lt=end_date
        ).select_related('student', 'student__group')
        
        revenue = 0
        students = []
        
        for payment in payments:
            student = payment.student
            expected_fee = student.get_monthly_fee()
            amount_paid = float(payment.amount_paid)
            
            revenue += amount_paid
            
            students.append({
                'name': student.full_name,
                'financial_status': student.get_financial_status_display(),
                'expected_fee': float(expected_fee),
                'amount_paid': amount_paid,
                'payment_status': payment.get_status_display(),
                'sessions_attended': payment.sessions_attended
            })
        
        return {
            'revenue': revenue,
            'students': students
        }
