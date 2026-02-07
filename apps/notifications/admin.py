from django.contrib import admin
from .models import WhatsAppMessage, WhatsAppTemplate


@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = ['phone_number', 'message_type', 'status', 'sent_at', 'sent_by']
    list_filter = ['status', 'message_type', 'created_at']
    search_fields = ['phone_number', 'message_text', 'student__full_name']
    readonly_fields = ['message_id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('المعلومات الأساسية', {
            'fields': ('phone_number', 'message_text', 'message_type')
        }),
        ('الارتباطات', {
            'fields': ('student', 'group', 'sent_by'),
            'classes': ('collapse',)
        }),
        ('الحالة', {
            'fields': ('status', 'error_message', 'sent_at', 'delivered_at')
        }),
        ('ملاحظات', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('التواريخ', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        return False


@admin.register(WhatsAppTemplate)
class WhatsAppTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'message_text']
    readonly_fields = ['template_id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('المعلومات الأساسية', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('محتوى الرسالة', {
            'fields': ('message_text',)
        }),
        ('التواريخ', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
