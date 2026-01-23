from django.contrib import admin
from .models import Session, Attendance


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ['session_date', 'group', 'teacher_attended', 'notification_sent', 'is_cancelled']
    list_filter = ['session_date', 'is_cancelled', 'notification_sent', 'group']
    search_fields = ['group__group_name', 'cancellation_reason']
    ordering = ['-session_date']
    
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
    )


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['student', 'session', 'scan_time', 'status', 'supervisor']
    list_filter = ['status', 'scan_time']
    search_fields = ['student__full_name', 'student__barcode']
    ordering = ['-scan_time']
    readonly_fields = ['scan_time', 'created_at']
