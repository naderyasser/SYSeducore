from django.contrib import admin
from django.db.models import Count, Q

from .models import Session, Attendance, ActivityLog, ExceptionRecord


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ['session_date', 'group', 'teacher_attended', 'notification_sent', 'is_cancelled', 'get_attendance_count', 'created_at']
    list_filter = ['session_date', 'is_cancelled', 'notification_sent', 'teacher_attended', 'group']
    list_editable = ['is_cancelled', 'notification_sent']  # تعديل سريع
    search_fields = ['group__group_name', 'cancellation_reason']
    ordering = ['-session_date']
    date_hierarchy = 'session_date'

    fieldsets = (
        ('معلومات الحصة', {
            'fields': ('group', 'session_date', 'is_cancelled', 'cancellation_reason')
        }),
        ('حضور المدرس', {
            'fields': ('teacher_attended', 'teacher_checkin_time')
        }),
        ('الإشعارات', {
            'fields': ('notification_sent',)
        }),
        ('معلومات النظام', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at']

    actions = ['mark_teacher_attended', 'cancel_sessions', 'mark_notified']

    def get_queryset(self, request):
        """
        Annotate the counts the list column needs. Reading them off ``obj``
        cost two queries per row (N+1) on every page of the changelist.
        """
        return super().get_queryset(request).select_related('group').annotate(
            _present_count=Count('attendances', filter=Q(attendances__status='present')),
            _attendance_count=Count('attendances'),
        )

    def get_attendance_count(self, obj):
        """عدد الطلاب الحاضرين"""
        return f'{obj._present_count}/{obj._attendance_count}'
    get_attendance_count.short_description = 'الحضور'

    def mark_teacher_attended(self, request, queryset):
        """تسجيل حضور المدرس"""
        from django.utils import timezone
        count = queryset.update(teacher_attended=True, teacher_checkin_time=timezone.now())
        self.message_user(request, f'تم تسجيل حضور المدرس لـ {count} حصة')
    mark_teacher_attended.short_description = "✅ تسجيل حضور المدرس"

    def cancel_sessions(self, request, queryset):
        """إلغاء الحصص المحددة"""
        count = queryset.update(is_cancelled=True)
        self.message_user(request, f'تم إلغاء {count} حصة')
    cancel_sessions.short_description = "❌ إلغاء الحصص"

    def mark_notified(self, request, queryset):
        """تحديد كـ "تم الإشعار"»"""
        count = queryset.update(notification_sent=True)
        self.message_user(request, f'تم تحديد {count} حصة كـ "تم الإشعار"')
    mark_notified.short_description = "📧 تحديد: تم الإشعار"


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['student', 'session', 'scan_time', 'status', 'supervisor', 'rejection_reason']
    list_filter = ['status', 'scan_time', 'session__group', 'supervisor']
    list_editable = ['status']  # تعديل سريع للحالة
    search_fields = ['student__full_name', 'student__student_code', 'rejection_reason']
    ordering = ['-scan_time']
    date_hierarchy = 'scan_time'
    autocomplete_fields = ['student', 'session']

    fieldsets = (
        ('معلومات الحضور', {
            'fields': ('student', 'session', 'status', 'rejection_reason')
        }),
        ('معلومات التسجيل', {
            'fields': ('scan_time', 'supervisor')
        }),
        ('معلومات النظام', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at']  # السماح بتعديل scan_time

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'student', 'session', 'session__group', 'supervisor'
        )

    actions = ['mark_present', 'mark_late', 'mark_absent', 'delete_attendances']

    def mark_present(self, request, queryset):
        """تحديد الحالة: حاضر"""
        count = queryset.update(status='present', rejection_reason='')
        self.message_user(request, f'تم تحديد {count} سجل كـ "حاضر"')
    mark_present.short_description = "✅ تحديد: حاضر"

    def mark_late(self, request, queryset):
        """تحديد الحالة: متأخر"""
        count = queryset.update(status='late', rejection_reason='')
        self.message_user(request, f'تم تحديد {count} سجل كـ "متأخر"')
    mark_late.short_description = "⏰ تحديد: متأخر"

    def mark_absent(self, request, queryset):
        """تحديد الحالة: غائب"""
        count = queryset.update(status='absent')
        self.message_user(request, f'تم تحديد {count} سجل كـ "غائب"')
    mark_absent.short_description = "❌ تحديد: غائب"

    def delete_attendances(self, request, queryset):
        """حذف سجلات الحضور المحددة"""
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f'تم حذف {count} سجل حضور', level='WARNING')
    delete_attendances.short_description = "🗑️ حذف السجلات"


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """إدارة سجلات النشاط - من قام بكل عملية"""
    list_display = ['user', 'action', 'description', 'target_model', 'ip_address', 'created_at']
    list_filter = ['action', 'user', 'created_at']
    search_fields = ['description', 'user__username', 'user__first_name']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    readonly_fields = ['user', 'action', 'description', 'target_model', 'target_id', 'ip_address', 'created_at']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

    def has_add_permission(self, request):
        return False  # Logs are created programmatically only

    def has_change_permission(self, request, obj=None):
        return False  # Read-only


@admin.register(ExceptionRecord)
class ExceptionRecordAdmin(admin.ModelAdmin):
    list_display = ['student', 'exception_type', 'reason_type', 'group', 'session',
                    'approved_by', 'is_active', 'created_at']
    list_filter = ['exception_type', 'reason_type', 'is_active', 'created_at']
    search_fields = ['student__full_name', 'student__student_code', 'custom_reason',
                     'group__group_name']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    autocomplete_fields = ['student', 'group', 'session', 'approved_by']
    readonly_fields = ['created_at']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'student', 'group', 'session', 'approved_by'
        )

    fieldsets = (
        ('معلومات الاستثناء', {
            'fields': ('student', 'group', 'session', 'exception_type', 'reason_type', 'custom_reason')
        }),
        ('الموافقة', {
            'fields': ('approved_by', 'is_active')
        }),
        ('معلومات النظام', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    actions = ['deactivate_exceptions']

    def deactivate_exceptions(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f'تم إلغاء تنشيط {count} استثناء')
    deactivate_exceptions.short_description = "إلغاء تنشيط الاستثناءات المحددة"
