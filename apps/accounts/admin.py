from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import (
    UserChangeForm as BaseUserChangeForm,
    UserCreationForm as BaseUserCreationForm,
)
from .models import User


class UserCreationForm(BaseUserCreationForm):
    """Hashes the password on creation (django.contrib.auth.forms bound to our custom model)."""
    class Meta(BaseUserCreationForm.Meta):
        model = User


class UserChangeForm(BaseUserChangeForm):
    """Renders the password as a read-only hash instead of an editable field."""
    class Meta(BaseUserChangeForm.Meta):
        model = User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm

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
    add_fieldsets = (
        ('معلومات المستخدم', {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'email', 'first_name', 'last_name'),
        }),
        ('الدور والصلاحيات', {
            'fields': ('role', 'is_active', 'is_staff', 'is_superuser'),
        }),
        ('معلومات إضافية', {
            'fields': ('phone',),
        }),
    )

    readonly_fields = ['last_login', 'date_joined']
