from django.contrib import admin
from .models import Teacher, Group


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'email', 'specialization', 'phone', 'is_active']
    list_filter = ['is_active', 'specialization']
    search_fields = ['full_name', 'email', 'phone']
    ordering = ['full_name']


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['group_name', 'teacher', 'schedule_day', 'schedule_time', 'standard_fee', 'is_active']
    list_filter = ['schedule_day', 'is_active', 'teacher']
    search_fields = ['group_name', 'teacher__full_name']
    ordering = ['group_name']
    
    fieldsets = (
        ('معلومات المجموعة', {
            'fields': ('group_name', 'teacher', 'is_active')
        }),
        ('الجدول', {
            'fields': ('schedule_day', 'schedule_time', 'grace_period')
        }),
        ('المالية', {
            'fields': ('standard_fee', 'center_percentage')
        }),
    )
