from django.contrib import admin
from .models import Payment


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

    actions = ['mark_paid', 'mark_unpaid', 'mark_partial', 'clear_payments']

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
