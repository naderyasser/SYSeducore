from django.contrib import admin
from .models import Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['barcode', 'full_name', 'group', 'financial_status', 'parent_phone', 'is_active']
    list_filter = ['financial_status', 'is_active', 'group']
    search_fields = ['barcode', 'full_name', 'parent_phone']
    ordering = ['full_name']
    
    fieldsets = (
        ('معلومات الطالب', {
            'fields': ('full_name', 'barcode', 'parent_phone', 'is_active')
        }),
        ('المجموعة', {
            'fields': ('group',)
        }),
        ('الحالة المالية', {
            'fields': ('financial_status', 'custom_fee')
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']
