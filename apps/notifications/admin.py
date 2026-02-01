"""
Notification Admin Interface
Complete admin for templates, preferences, logs, and cost tracking
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Count, Sum, Q
from .models import (
    NotificationLog,
    NotificationTemplate,
    NotificationPreference,
    NotificationCost
)


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    """
    Admin for managing notification templates
    """
    list_display = [
        'template_type_display',
        'template_name',
        'version',
        'is_active',
        'created_at',
        'preview_button'
    ]
    list_filter = ['template_type', 'is_active', 'created_at']
    search_fields = ['template_name', 'content_arabic']
    readonly_fields = ['version', 'created_at', 'updated_at']
    
    fieldsets = (
        ('معلومات القالب', {
            'fields': ('template_type', 'template_name', 'is_active')
        }),
        ('محتوى القالب', {
            'fields': (
                'content_arabic',
                'content_english',
                'available_variables'
            )
        }),
        ('التحكم بالإصدار', {
            'fields': ('version', 'created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def template_type_display(self, obj):
        """Display template type with emoji"""
        icons = {
            'attendance_success': '🟢',
            'late_block': '🔴',
            'financial_block_new': '🟡',
            'financial_block_debt': '🟡',
            'payment_reminder': '📢',
            'payment_confirmation': '🙏',
        }
        icon = icons.get(obj.template_type, '📋')
        return format_html('{} {}', icon, obj.get_template_type_display())
    template_type_display.short_description = 'نوع القالب'
    
    def preview_button(self, obj):
        """Add preview button"""
        url = reverse('admin:preview_notification_template', args=[obj.id])
        return format_html(
            '<a href="{}" class="button" target="_blank">معاينة</a>',
            url
        )
    preview_button.short_description = 'معاينة'
    
    def save_model(self, request, obj, form, change):
        """Set created_by on new templates"""
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    """
    Admin for managing parent notification preferences
    """
    list_display = [
        'student_name',
        'attendance_success_enabled',
        'payment_reminder_enabled',
        'messages_last_hour',
        'last_message_time'
    ]
    list_filter = [
        'attendance_success_enabled',
        'payment_reminder_enabled',
        'payment_confirmation_enabled'
    ]
    search_fields = ['student__full_name', 'student__student_code']
    readonly_fields = ['messages_last_hour', 'last_message_time', 'created_at']
    
    fieldsets = (
        ('معلومات الطالب', {
            'fields': ('student',)
        }),
        ('تفضيلات الإشعارات الاختيارية', {
            'fields': (
                'attendance_success_enabled',
                'payment_reminder_enabled',
                'payment_confirmation_enabled'
            ),
            'description': 'يمكن تعطيل هذه الإشعارات حسب طلب ولي الأمر'
        }),
        ('إشعارات إلزامية', {
            'fields': (
                'late_block_enabled',
                'financial_block_enabled'
            ),
            'description': 'هذه الإشعارات إلزامية ولا يمكن تعطيلها'
        }),
        ('معلومات الحد', {
            'fields': (
                'messages_last_hour',
                'last_message_time'
            ),
            'classes': ('collapse',)
        }),
    )
    
    def student_name(self, obj):
        return obj.student.full_name
    student_name.short_description = 'الطالب'
    
    def has_add_permission(self, request):
        """Prevent manual creation - auto-created with student"""
        return False


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    """
    Admin for viewing notification logs with enhanced features
    """
    list_display = [
        'student_link',
        'notification_type_display',
        'status_badge_display',
        'phone_number',
        'sent_at',
        'retry_info',
        'cost_display'
    ]
    list_filter = [
        'notification_type',
        'status',
        'sent_at'
    ]
    search_fields = [
        'student_name',
        'phone_number',
        'message',
        'api_message_id'
    ]
    readonly_fields = [
        'student', 'student_name', 'phone_number',
        'notification_type', 'template_used',
        'message', 'status', 'api_message_id',
        'api_response', 'retry_count', 'max_retries',
        'next_retry_at', 'error_message', 'error_code',
        'cost', 'cost_recorded', 'sent_at', 'delivered_at',
        'created_at', 'context_data'
    ]
    ordering = ['-created_at']
    date_hierarchy = 'sent_at'
    
    fieldsets = (
        ('معلومات الإشعار', {
            'fields': (
                'student',
                'student_name',
                'phone_number',
                'notification_type',
                'template_used'
            )
        }),
        ('محتوى الرسالة', {
            'fields': ('message', 'context_data'),
            'classes': ('collapse',)
        }),
        ('الحالة والتسليم', {
            'fields': (
                'status',
                'sent_at',
                'delivered_at',
                'api_message_id',
                'api_response'
            )
        }),
        ('إعادة المحاولة', {
            'fields': (
                'retry_count',
                'max_retries',
                'next_retry_at'
            ),
            'classes': ('collapse',)
        }),
        ('الأخطاء', {
            'fields': ('error_message', 'error_code'),
            'classes': ('collapse',)
        }),
        ('التكلفة', {
            'fields': ('cost', 'cost_recorded')
        }),
    )
    
    def student_link(self, obj):
        """Link to student detail"""
        if obj.student:
            url = reverse('admin:students_student_change', args=[obj.student.student_id])
            return format_html('<a href="{}">{}</a>', url, obj.student_name)
        return obj.student_name
    student_link.short_description = 'الطالب'
    
    def notification_type_display(self, obj):
        """Display notification type with icon"""
        return format_html(
            '<i class="{}"></i> {}',
            obj.type_icon,
            obj.get_notification_type_display()
        )
    notification_type_display.short_description = 'نوع الإشعار'
    notification_type_display.allow_tags = True
    
    def status_badge_display(self, obj):
        """Display status as badge"""
        colors = {
            'pending': 'warning',
            'sent': 'info',
            'delivered': 'success',
            'failed': 'danger',
            'retrying': 'secondary'
        }
        color = colors.get(obj.status, 'secondary')
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge_display.short_description = 'الحالة'
    
    def retry_info(self, obj):
        """Display retry information"""
        if obj.retry_count > 0:
            return format_html(
                '{}/{} {}',
                obj.retry_count,
                obj.max_retries,
                '🔄' if obj.status == 'retrying' else '❌'
            )
        return '-'
    retry_info.short_description = 'إعادة المحاولة'
    
    def cost_display(self, obj):
        """Display cost"""
        return format_html('{} ج.م', obj.cost)
    cost_display.short_description = 'التكلفة'
    
    def has_add_permission(self, request):
        """Prevent manual creation - auto-created by system"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Logs are read-only"""
        return False
    
    actions = ['retry_failed_notifications']
    
    def retry_failed_notifications(self, request, queryset):
        """Admin action to retry failed notifications"""
        from .tasks import retry_failed_notifications_task
        
        count = 0
        for log in queryset.filter(status='failed', retry_count__lt=3):
            if log.can_retry():
                log.schedule_retry()
                count += 1
        
        self.message_user(
            request,
            f'تم جدولة إعادة محاولة {count} إشعار'
        )
    retry_failed_notifications.short_description = 'إعادة محاولة الإشعارات الفاشلة'


@admin.register(NotificationCost)
class NotificationCostAdmin(admin.ModelAdmin):
    """
    Admin for viewing notification costs
    """
    list_display = [
        'month_display',
        'total_messages',
        'total_cost_display',
        'cost_per_message',
        'currency'
    ]
    list_filter = ['month', 'currency']
    readonly_fields = [
        'month', 'total_messages', 'total_cost',
        'cost_per_message', 'currency', 'created_at', 'updated_at'
    ]
    ordering = ['-month']
    date_hierarchy = 'month'
    
    fieldsets = (
        ('ملخص الشهر', {
            'fields': (
                'month',
                'total_messages',
                'total_cost',
                'cost_per_message',
                'currency'
            )
        }),
        ('معلومات التعديل', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def month_display(self, obj):
        """Display month in Arabic"""
        months_ar = [
            'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
            'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'
        ]
        return format_html(
            '{} {}',
            months_ar[obj.month.month - 1],
            obj.month.year
        )
    month_display.short_description = 'الشهر'
    
    def total_cost_display(self, obj):
        """Display total cost"""
        return format_html(
            '<span style="color: {};">{} {}</span>',
            'red' if obj.total_cost > 500 else 'green',
            obj.total_cost,
            obj.currency
        )
    total_cost_display.short_description = 'التكلفة الإجمالية'
    
    def has_add_permission(self, request):
        """Prevent manual creation - auto-created by system"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Cost records are read-only"""
        return False


# ========================================
# Dashboard Custom Views
# ========================================

class NotificationDashboardAdmin(admin.ModelAdmin):
    """
    Custom dashboard for notification statistics
    """
    change_list_template = 'admin/notifications_dashboard.html'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


# ========================================
# Inline Admins
# ========================================

class NotificationPreferenceInline(admin.TabularInline):
    """
    Inline admin for notification preferences in student detail
    """
    model = NotificationPreference
    extra = 0
    readonly_fields = [
        'attendance_success_enabled',
        'late_block_enabled',
        'financial_block_enabled',
        'payment_reminder_enabled',
        'payment_confirmation_enabled'
    ]
    can_delete = False
    
    def has_add_permission(self, request, obj):
        return False


# ========================================
# Admin Site Customization
# ========================================

admin.site.site_header = 'مركز التعليم - إدارة النظام'
admin.site.site_title = 'مركز التعليم'
admin.site.index_title = 'لوحة التحكم الرئيسية'
