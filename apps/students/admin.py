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
    list_display = ['student_code', 'full_name', 'get_groups', 'parent_phone', 'is_active']
    list_filter = ['is_active', 'created_at']
    list_editable = ['is_active']  # تعديل سريع من القائمة
    search_fields = ['student_code', 'full_name', 'parent_phone']
    ordering = ['full_name']
    inlines = [StudentGroupEnrollmentInline]
    date_hierarchy = 'created_at'

    fieldsets = (
        ('معلومات الطالب', {
            'fields': ('full_name', 'student_code', 'parent_phone', 'is_active')
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)  # قابلة للطي
        }),
    )

    readonly_fields = ['created_at', 'updated_at']

    actions = ['activate_students', 'deactivate_students', 'export_students']

    def get_groups(self, obj):
        """عرض المجموعات المسجل فيها الطالب"""
        groups = obj.groups.all()
        if groups:
            return ", ".join([g.group_name for g in groups])
        return "لا توجد مجموعات"
    get_groups.short_description = 'المجموعات'

    def activate_students(self, request, queryset):
        """تفعيل الطلاب المحددين"""
        count = queryset.update(is_active=True)
        self.message_user(request, f'تم تفعيل {count} طالب/طالبة')
    activate_students.short_description = "✅ تفعيل الطلاب المحددين"

    def deactivate_students(self, request, queryset):
        """إلغاء تفعيل الطلاب المحددين"""
        count = queryset.update(is_active=False)
        self.message_user(request, f'تم إلغاء تفعيل {count} طالب/طالبة')
    deactivate_students.short_description = "❌ إلغاء تفعيل الطلاب المحددين"

    def export_students(self, request, queryset):
        """تصدير بيانات الطلاب (للإضافة لاحقاً)"""
        self.message_user(request, f'تم تحديد {queryset.count()} طالب/طالبة للتصدير')
    export_students.short_description = "📥 تصدير البيانات"


@admin.register(StudentGroupEnrollment)
class StudentGroupEnrollmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'group', 'financial_status', 'custom_fee', 'is_active', 'enrolled_at']
    list_filter = ['financial_status', 'is_active', 'group', 'enrolled_at']
    list_editable = ['financial_status', 'custom_fee', 'is_active']  # تعديل سريع
    search_fields = ['student__full_name', 'student__student_code', 'group__group_name']
    ordering = ['-enrolled_at']
    autocomplete_fields = ['student', 'group']
    date_hierarchy = 'enrolled_at'

    fieldsets = (
        ('التسجيل', {
            'fields': ('student', 'group', 'is_active')
        }),
        ('الحالة المالية', {
            'fields': ('financial_status', 'custom_fee')
        }),
        ('معلومات النظام', {
            'fields': ('enrolled_at',),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['enrolled_at']

    actions = ['set_normal_status', 'set_exempt_status', 'activate_enrollments']

    def set_normal_status(self, request, queryset):
        """تعيين الحالة المالية: عادي"""
        count = queryset.update(financial_status='normal', custom_fee=None)
        self.message_user(request, f'تم تعيين {count} تسجيل كـ "عادي"')
    set_normal_status.short_description = "💰 تعيين: عادي"

    def set_exempt_status(self, request, queryset):
        """تعيين الحالة المالية: إعفاء كامل"""
        count = queryset.update(financial_status='exempt', custom_fee=None)
        self.message_user(request, f'تم تعيين {count} تسجيل كـ "إعفاء كامل"')
    set_exempt_status.short_description = "🎁 تعيين: إعفاء كامل"

    def activate_enrollments(self, request, queryset):
        """تفعيل التسجيلات المحددة"""
        count = queryset.update(is_active=True)
        self.message_user(request, f'تم تفعيل {count} تسجيل')
    activate_enrollments.short_description = "✅ تفعيل التسجيلات"
