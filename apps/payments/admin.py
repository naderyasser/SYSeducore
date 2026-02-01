from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum
from .models import Payment, PaymentAuditLog
from apps.students.models import StudentGroupEnrollment


@admin.register(PaymentAuditLog)
class PaymentAuditLogAdmin(admin.ModelAdmin):
    """Admin interface for Payment Audit Log"""
    list_display = [
        'created_at', 'student', 'group', 'action_display',
        'amount', 'sessions_count', 'performed_by'
    ]
    list_filter = ['action', 'created_at', 'group']
    search_fields = [
        'student__full_name', 'student__student_code',
        'group__group_name', 'performed_by__username'
    ]
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    readonly_fields = [
        'created_at', 'student', 'group', 'action', 'old_value',
        'new_value', 'amount', 'sessions_count', 'notes',
        'performed_by', 'ip_address'
    ]

    fieldsets = (
        ('معلومات العملية', {
            'fields': ('action', 'student', 'group', 'created_at')
        }),
        ('القيم', {
            'fields': ('old_value', 'new_value', 'amount', 'sessions_count')
        }),
        ('معلومات إضافية', {
            'fields': ('notes', 'performed_by', 'ip_address')
        }),
    )

    def has_add_permission(self, request):
        """منع الإضافة اليدوية"""
        return False

    def has_change_permission(self, request, obj=None):
        """منع التعديل"""
        return False

    def action_display(self, obj):
        """عرض الإجراء بشكل ملون"""
        action_colors = {
            'payment_recorded': 'success',
            'credit_adjustment': 'info',
            'fee_changed': 'warning',
            'status_changed': 'secondary',
            'block_applied': 'danger',
            'block_removed': 'success',
            'bulk_payment': 'primary',
        }
        color = action_colors.get(obj.action, 'secondary')
        return format_html(
            '<span class="badge badge-{}">{}</span>',
            color,
            obj.get_action_display()
        )
    action_display.short_description = 'الإجراء'


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['student', 'group', 'month', 'amount_due', 'amount_paid', 'status', 'sessions_attended', 'payment_date']
    list_filter = ['status', 'month', 'payment_date', 'group']
    list_editable = ['status', 'amount_paid']  # تعديل سريع
    search_fields = ['student__full_name', 'student__student_code', 'group__group_name']
    ordering = ['-month']
    date_hierarchy = 'month'
    autocomplete_fields = ['student', 'group']

    fieldsets = (
        ('معلومات الطالب', {
            'fields': ('student', 'group', 'month')
        }),
        ('المدفوعات', {
            'fields': ('amount_due', 'amount_paid', 'status', 'payment_date')
        }),
        ('الحضور', {
            'fields': ('sessions_attended',)
        }),
        ('ملاحظات', {
            'fields': ('notes',)
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at', 'updated_at']

    actions = [
        'mark_paid', 'mark_unpaid', 'mark_partial', 'clear_payments',
        'bulk_record_payment'
    ]

    def mark_paid(self, request, queryset):
        """تحديد كـ "مدفوع"»"""
        from django.utils import timezone
        count = 0
        for payment in queryset:
            payment.status = 'paid'
            payment.amount_paid = payment.amount_due
            payment.payment_date = timezone.now().date()
            payment.save()
            count += 1
        self.message_user(request, f'تم تحديد {count} دفعة كـ "مدفوع"')
    mark_paid.short_description = "✅ تحديد: مدفوع"

    def mark_unpaid(self, request, queryset):
        """تحديد كـ "غير مدفوع"»"""
        count = queryset.update(status='unpaid', amount_paid=0, payment_date=None)
        self.message_user(request, f'تم تحديد {count} دفعة كـ "غير مدفوع"')
    mark_unpaid.short_description = "❌ تحديد: غير مدفوع"

    def mark_partial(self, request, queryset):
        """تحديد كـ "مدفوع جزئياً"»"""
        count = queryset.update(status='partial')
        self.message_user(request, f'تم تحديد {count} دفعة كـ "مدفوع جزئياً"')
    mark_partial.short_description = "⚠️ تحديد: مدفوع جزئياً"

    def clear_payments(self, request, queryset):
        """مسح المدفوعات (تصفير)"""
        count = queryset.update(amount_paid=0, status='unpaid', payment_date=None)
        self.message_user(request, f'تم تصفير {count} دفعة', level='WARNING')
    clear_payments.short_description = "🔄 تصفير المدفوعات"

    def bulk_record_payment(self, request, queryset):
        """تسجيل دفع جماعي وتحديث الائتمان"""
        from .services import CreditService
        from django.contrib import messages
        
        count = 0
        for payment in queryset:
            try:
                # حساب عدد الحصص (نفترض 4 حصص كحد أدنى للشهر)
                sessions_count = max(4, payment.sessions_attended)
                amount_per_session = payment.amount_due / sessions_count if sessions_count > 0 else 0
                
                # تسجيل الدفع
                result = CreditService.record_payment_and_update_credit(
                    student=payment.student,
                    group=payment.group,
                    amount=payment.amount_due,
                    sessions_count=sessions_count,
                    performed_by=request.user,
                    notes=f'دفع جماعي من لوحة الإدارة - {payment.month.strftime("%Y-%m")}'
                )
                
                if result['success']:
                    count += 1
            except Exception as e:
                messages.warning(request, f'خطأ في {payment.student.full_name}: {str(e)}')
        
        if count > 0:
            self.message_user(
                request,
                f'تم تسجيل دفع {count} طالب وتحديث الائتمان',
                level='SUCCESS'
            )
    bulk_record_payment.short_description = "💰 تسجيل دفع جماعي (تحديث الائتمان)"
