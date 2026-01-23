from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['student', 'month', 'amount_due', 'amount_paid', 'status', 'sessions_attended']
    list_filter = ['status', 'month']
    search_fields = ['student__full_name', 'student__barcode']
    ordering = ['-month']
    
    fieldsets = (
        ('معلومات الطالب', {
            'fields': ('student', 'month')
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
    )
    
    readonly_fields = ['created_at', 'updated_at']
