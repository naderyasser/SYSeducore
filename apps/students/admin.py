from django.contrib import admin
from .models import Student, StudentGroupEnrollment


class StudentGroupEnrollmentInline(admin.TabularInline):
    """
    Inline admin للمجموعات المسجل فيها الطالب
    """
    model = StudentGroupEnrollment
    extra = 1
    fields = ['group', 'financial_status', 'custom_fee', 'is_active']
    autocomplete_fields = ['group']


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['barcode', 'full_name', 'get_groups', 'parent_phone', 'is_active']
    list_filter = ['is_active']
    search_fields = ['barcode', 'full_name', 'parent_phone']
    ordering = ['full_name']
    inlines = [StudentGroupEnrollmentInline]

    fieldsets = (
        ('معلومات الطالب', {
            'fields': ('full_name', 'barcode', 'parent_phone', 'is_active')
        }),
    )

    readonly_fields = ['created_at', 'updated_at']

    def get_groups(self, obj):
        """عرض المجموعات المسجل فيها الطالب"""
        return ", ".join([g.group_name for g in obj.groups.all()])
    get_groups.short_description = 'المجموعات'


@admin.register(StudentGroupEnrollment)
class StudentGroupEnrollmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'group', 'financial_status', 'custom_fee', 'is_active', 'enrolled_at']
    list_filter = ['financial_status', 'is_active', 'group']
    search_fields = ['student__full_name', 'student__barcode', 'group__group_name']
    ordering = ['-enrolled_at']
    autocomplete_fields = ['student', 'group']

    fieldsets = (
        ('التسجيل', {
            'fields': ('student', 'group', 'is_active')
        }),
        ('الحالة المالية', {
            'fields': ('financial_status', 'custom_fee')
        }),
    )

    readonly_fields = ['enrolled_at']
