from django.contrib import admin
from .models import Session, Attendance


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

    def get_attendance_count(self, obj):
        """عدد الطلاب الحاضرين"""
        count = obj.attendances.filter(status='present').count()
        total = obj.attendances.count()
        return f'{count}/{total}'
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
