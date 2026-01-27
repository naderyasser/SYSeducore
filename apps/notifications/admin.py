from django.contrib import admin
from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ['student_name', 'phone_number', 'notification_type', 'status', 'sent_at']
    list_filter = ['notification_type', 'status', 'sent_at']
    search_fields = ['student_name', 'phone_number', 'message']
    readonly_fields = ['student', 'student_name', 'phone_number', 'notification_type',
                       'message', 'status', 'error_message', 'sent_at', 'created_at']
    ordering = ['-sent_at']
    date_hierarchy = 'sent_at'
