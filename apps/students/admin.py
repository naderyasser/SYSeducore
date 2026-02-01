from django.contrib import admin
from django.utils.html import format_html
from django.db.models import F
from .models import Student, StudentGroupEnrollment


class StudentGroupEnrollmentInline(admin.TabularInline):
    """
    Inline admin للمجموعات المسجل فيها الطالب
    """
    model = StudentGroupEnrollment
    extra = 1
    fields = ['group', 'financial_status', 'custom_fee', 'is_new_student', 'credit_balance', 'is_active']
    autocomplete_fields = ['group']


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['student_code', 'full_name', 'get_groups', 'parent_phone', 'qr_code_status', 'is_active']
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
        ('رمز الاستجابة السريعة (QR)', {
            'fields': ('qr_code_display', 'qr_code_base64', 'qr_code_generated_at'),
            'classes': ('collapse',),
            'description': 'رمز QR للطالب - يتم توليده تلقائياً عند إنشاء الطالب'
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)  # قابلة للطي
        }),
    )

    readonly_fields = ['created_at', 'updated_at', 'qr_code_display', 'qr_code_generated_at']

    actions = ['activate_students', 'deactivate_students', 'export_students', 'generate_qr_codes', 'print_qr_codes']

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

    def qr_code_status(self, obj):
        """Display QR code status in list"""
        if obj.qr_code_base64:
            return format_html('<span class="badge badge-success">✅ QR موجود</span>')
        return format_html('<span class="badge badge-warning">⚠️ غير موجود</span>')
    qr_code_status.short_description = 'رمز QR'

    def qr_code_display(self, obj):
        """Display QR code in admin detail view"""
        if obj.qr_code_base64:
            return format_html(
                '<div style="text-align: center;">'
                '<img src="{}" style="width: 200px; height: 200px; border: 2px solid #ddd; border-radius: 8px;" />'
                '<p style="margin-top: 10px; font-weight: bold;">{}</p>'
                '</div>',
                obj.qr_code_base64,
                obj.student_code
            )
        return format_html('<p style="color: #999;">لم يتم توليد رمز QR بعد</p>')
    qr_code_display.short_description = 'معاينة رمز QR'

    def generate_qr_codes(self, request, queryset):
        """Generate QR codes for selected students"""
        count = 0
        for student in queryset:
            if not student.qr_code_base64:
                try:
                    student.generate_qr_code()
                    count += 1
                except Exception as e:
                    self.message_user(request, f'خطأ في توليد QR للطالب {student.student_code}: {e}', level='ERROR')
        if count > 0:
            self.message_user(request, f'تم توليد رموز QR لـ {count} طالب/طالبة')
        else:
            self.message_user(request, 'جميع الطلاب المحددين لديهم رموز QR بالفعل')
    generate_qr_codes.short_description = "🔲 توليد رموز QR"

    def print_qr_codes(self, request, queryset):
        """Print QR codes for selected students (redirects to print view)"""
        from django.urls import reverse
        from django.http import HttpResponseRedirect
        
        # Store selected student IDs in session
        request.session['qr_print_student_ids'] = list(queryset.values_list('student_id', flat=True))
        
        # Redirect to print view
        print_url = reverse('students:print_qr_codes')
        self.message_user(request, f'سيتم طباعة رموز QR لـ {queryset.count()} طالب/طالبة')
        return HttpResponseRedirect(print_url)
    print_qr_codes.short_description = "🖨️ طباعة رموز QR"


@admin.register(StudentGroupEnrollment)
class StudentGroupEnrollmentAdmin(admin.ModelAdmin):
    list_display = [
        'student', 'group', 'financial_status', 'custom_fee',
        'is_new_student', 'credit_balance', 'credit_status_display',
        'sessions_attended', 'sessions_paid_for', 'is_active', 'enrolled_at'
    ]
    list_filter = [
        'financial_status', 'is_active', 'is_new_student',
        'is_financially_blocked', 'group', 'enrolled_at'
    ]
    list_editable = [
        'financial_status', 'custom_fee', 'is_new_student',
        'credit_balance', 'is_active'
    ]  # تعديل سريع
    search_fields = [
        'student__full_name', 'student__student_code', 'group__group_name'
    ]
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
        ('نظام الائتمان (Credit System)', {
            'fields': (
                'is_new_student', 'credit_balance',
                'sessions_attended', 'sessions_paid_for',
                'last_payment_date', 'last_payment_amount',
                'is_financially_blocked', 'financial_block_reason'
            ),
            'classes': ('collapse',),
            'description': 'نظام الائتمان: الطلاب الجدد = 0 حصة، الطلاب القدامى = 2 حصص'
        }),
        ('معلومات النظام', {
            'fields': ('enrolled_at',),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = [
        'enrolled_at', 'sessions_attended', 'sessions_paid_for',
        'last_payment_date', 'credit_status_display'
    ]

    actions = [
        'set_normal_status', 'set_exempt_status', 'activate_enrollments',
        'mark_as_new_student', 'mark_as_returning_student',
        'reset_credit_balance', 'clear_financial_block'
    ]

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

    def mark_as_new_student(self, request, queryset):
        """تعيين الطلاب كطلاب جدد"""
        count = queryset.update(
            is_new_student=True,
            credit_balance=0,
            is_financially_blocked=False,
            financial_block_reason=''
        )
        self.message_user(request, f'تم تعيين {count} طالب كـ "طالب جديد" (رصيد = 0)')
    mark_as_new_student.short_description = "🆕 تعيين: طالب جديد (رصيد 0)"

    def mark_as_returning_student(self, request, queryset):
        """تعيين الطلاب كطلاب قدامى"""
        count = queryset.update(
            is_new_student=False,
            credit_balance=2,
            is_financially_blocked=False,
            financial_block_reason=''
        )
        self.message_user(request, f'تم تعيين {count} طالب كـ "طالب قديم" (رصيد = 2)')
    mark_as_returning_student.short_description = "🔄 تعيين: طالب قديم (رصيد 2)"

    def reset_credit_balance(self, request, queryset):
        """إعادة تعيين رصيد الائتمان"""
        for enrollment in queryset:
            if enrollment.is_new_student:
                enrollment.credit_balance = 0
            else:
                enrollment.credit_balance = 2
            enrollment.save()
        self.message_user(request, f'تم إعادة تعيين رصيد الائتمان لـ {queryset.count()} طالب')
    reset_credit_balance.short_description = "🔄 إعادة تعيين رصيد الائتمان"

    def clear_financial_block(self, request, queryset):
        """إزالة الحظر المالي"""
        count = queryset.update(
            is_financially_blocked=False,
            financial_block_reason=''
        )
        self.message_user(request, f'تم إزالة الحظر المالي لـ {count} طالب')
    clear_financial_block.short_description = "🔓 إزالة الحظر المالي"

    def credit_status_display(self, obj):
        """عرض حالة الائتمان بشكل ملون"""
        debt = obj.sessions_attended - obj.sessions_paid_for
        remaining = obj.credit_balance - debt
        
        if obj.financial_status == 'exempt':
            return format_html('<span class="badge badge-success">إعفاء كامل</span>')
        elif obj.is_financially_blocked:
            return format_html(
                '<span class="badge badge-danger">محظور - {}</span>',
                obj.financial_block_reason or 'سبب غير محدد'
            )
        elif remaining < 0:
            return format_html(
                '<span class="badge badge-danger">دين {} حصة</span>',
                abs(debt)
            )
        elif remaining == 0:
            return format_html('<span class="badge badge-warning">نفذ الرصيد</span>')
        elif remaining == 1:
            return format_html('<span class="badge badge-info">حصة متبقية</span>')
        else:
            return format_html(
                '<span class="badge badge-success">رصيد {} حصة</span>',
                remaining
            )
    credit_status_display.short_description = 'حالة الائتمان'
