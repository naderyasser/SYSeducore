from django.contrib import admin
from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['username', 'email', 'role', 'is_active', 'created_at']
    list_filter = ['role', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering = ['-created_at']
    
    fieldsets = (
        ('معلومات المستخدم', {
            'fields': ('username', 'password', 'email', 'first_name', 'last_name')
        }),
        ('الدور والصلاحيات', {
            'fields': ('role', 'is_active', 'is_staff', 'is_superuser')
        }),
        ('معلومات إضافية', {
            'fields': ('phone', 'last_login', 'date_joined')
        }),
    )
    
    readonly_fields = ['last_login', 'date_joined']
