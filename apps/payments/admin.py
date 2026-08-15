from django.contrib import admin

from apps.attendance.models import ActivityLog

from .models import Payment, PaymentAmountError, PaymentTransaction


class PaymentTransactionInline(admin.TabularInline):
    """
    سجل الحركات — read-only receipt trail.

    Money is never moved by editing a field: use the list actions, which
    write a ledger row and an ActivityLog entry.
    """
    model = PaymentTransaction
    extra = 0
    can_delete = False
    fields = ['created_at', 'amount', 'kind', 'created_by', 'note']
    readonly_fields = fields
    ordering = ['-created_at']

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['student', 'group', 'month', 'amount_due', 'amount_paid', 'status',
                    'is_exempt', 'sessions_attended', 'payment_date']
    list_filter = ['status', 'is_exempt', 'month', 'payment_date', 'group']
    # ``list_editable`` used to expose ``status`` and ``amount_paid``: money
    # could be rewritten from the list page, with the two fields free to
    # disagree and nothing recorded about who did it. Both are now derived
    # from the transaction ledger.
    search_fields = ['student__full_name', 'student__student_code', 'group__group_name']
    ordering = ['-month']
    date_hierarchy = 'month'
    autocomplete_fields = ['student', 'group']
    inlines = [PaymentTransactionInline]

    fieldsets = (
        ('معلومات الطالب', {
            'fields': ('student', 'group', 'month')
        }),
        ('المدفوعات', {
            'fields': ('amount_due', 'amount_paid', 'status', 'is_exempt', 'payment_date'),
            'description': (
                'المبلغ المدفوع والحالة يُحسبان تلقائياً من سجل الحركات بالأسفل. '
                'استخدم الإجراءات من صفحة القائمة لتسجيل أو تصفير الدفعات.'
            ),
        }),
        ('الحضور', {
            'fields': ('sessions_attended',)
        }),
        ('ملاحظات', {
            'fields': ('notes',)
        }),
        ('معلومات النظام', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['amount_paid', 'status', 'payment_date', 'created_by',
                       'created_at', 'updated_at']

    actions = ['mark_paid', 'mark_unpaid', 'clear_payments']

    def save_model(self, request, obj, form, change):
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        ActivityLog.log(
            user=request.user,
            action='payment_update' if change else 'payment_create',
            description=(
                f'{"تعديل" if change else "إنشاء"} دفعة من لوحة الإدارة: '
                f'{obj.student.full_name} — {obj.group.group_name} — '
                f'{obj.month.strftime("%Y-%m")}'
            ),
            target_model='Payment',
            target_id=obj.pk,
            request=request,
        )

    def _log_bulk(self, request, action, description, count):
        ActivityLog.log(
            user=request.user,
            action=action,
            description=f'{description} ({count} دفعة) من لوحة الإدارة',
            target_model='Payment',
            target_id=None,
            request=request,
        )

    @admin.action(description="✅ تحديد: مدفوع")
    def mark_paid(self, request, queryset):
        """تحديد كـ "مدفوع" — يسجّل حركة دفع بالمتبقي"""
        count = 0
        failed = 0
        for payment in queryset.select_related('student', 'group'):
            try:
                payment.settle_full(user=request.user, note='تسديد كامل من لوحة الإدارة')
            except PaymentAmountError:
                failed += 1
                continue
            count += 1
        self._log_bulk(request, 'payment_record', 'تسديد كامل', count)
        self.message_user(request, f'تم تحديد {count} دفعة كـ "مدفوع"')
        if failed:
            self.message_user(
                request, f'تعذر تسديد {failed} دفعة', level='WARNING',
            )

    @admin.action(description="❌ تحديد: غير مدفوع")
    def mark_unpaid(self, request, queryset):
        """تحديد كـ "غير مدفوع" — يعكس المبالغ المسجلة بحركة صريحة"""
        count = 0
        for payment in queryset.select_related('student', 'group'):
            payment.reverse_all(user=request.user, note='إلغاء التسديد من لوحة الإدارة')
            count += 1
        self._log_bulk(request, 'payment_update', 'إلغاء تسديد', count)
        self.message_user(request, f'تم تحديد {count} دفعة كـ "غير مدفوع"')

    @admin.action(description="🔄 تصفير المدفوعات")
    def clear_payments(self, request, queryset):
        """مسح المدفوعات (تصفير) — عملية خطرة، تُسجَّل بالكامل"""
        count = 0
        cleared_total = 0
        for payment in queryset.select_related('student', 'group'):
            cleared_total += payment.amount_paid or 0
            payment.reverse_all(user=request.user, note='تصفير المدفوعات من لوحة الإدارة')
            count += 1
        self._log_bulk(
            request, 'payment_update',
            f'تصفير مدفوعات بإجمالي {cleared_total} ج.م', count,
        )
        self.message_user(request, f'تم تصفير {count} دفعة', level='WARNING')


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    """سجل حركات الدفع — للعرض فقط، لا يُعدَّل ولا يُحذف."""
    list_display = ['transaction_id', 'payment', 'amount', 'kind', 'created_by', 'created_at']
    list_filter = ['kind', 'created_at']
    search_fields = [
        'payment__student__full_name',
        'payment__student__student_code',
        'note',
    ]
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    readonly_fields = ['payment', 'amount', 'kind', 'created_by', 'created_at', 'note']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
