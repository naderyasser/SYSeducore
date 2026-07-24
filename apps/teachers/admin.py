from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q

from .models import Teacher, Group, Room, Subject


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'education_stage', 'get_teachers_count']
    list_filter = ['education_stage']
    search_fields = ['name']
    ordering = ['name']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            teachers_count=Count('teachers', distinct=True)
        )

    @admin.display(description='عدد المدرسين', ordering='teachers_count')
    def get_teachers_count(self, obj):
        return obj.teachers_count


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ['name', 'capacity', 'is_active', 'get_groups_count', 'created_at']
    list_filter = ['is_active', 'created_at']
    list_editable = ['capacity', 'is_active']  # تعديل سريع
    search_fields = ['name']
    ordering = ['name']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('معلومات القاعة', {
            'fields': ('name', 'capacity', 'is_active')
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at', 'updated_at', 'get_groups_list']

    actions = ['activate_rooms', 'deactivate_rooms']

    def get_queryset(self, request):
        """Annotate the count so the changelist is not N+1 over rooms."""
        return super().get_queryset(request).annotate(
            active_groups_count=Count(
                'groups', filter=Q(groups__is_active=True), distinct=True
            )
        )

    @admin.display(description='عدد المجموعات', ordering='active_groups_count')
    def get_groups_count(self, obj):
        """عدد المجموعات في القاعة"""
        return f'{obj.active_groups_count} مجموعة'

    def get_groups_list(self, obj):
        """قائمة المجموعات في القاعة"""
        groups = obj.groups.filter(is_active=True).prefetch_related('schedules')
        parts = []
        for group in groups:
            schedule = " ، ".join(
                f"{entry.get_day_display()} {entry.start_time.strftime('%I:%M %p')}"
                f" - {entry.get_end_time().strftime('%I:%M %p')}"
                for entry in group.get_schedule_entries()
            )
            parts.append(f"{group.group_name} ({schedule or 'بدون مواعيد'})")
        return " | ".join(parts) if parts else "لا توجد مجموعات"
    get_groups_list.short_description = 'المجموعات المسجلة'

    def activate_rooms(self, request, queryset):
        """تفعيل القاعات المحددة"""
        count = queryset.update(is_active=True)
        self.message_user(request, f'تم تفعيل {count} قاعة')
    activate_rooms.short_description = "✅ تفعيل القاعات"

    def deactivate_rooms(self, request, queryset):
        """إلغاء تفعيل القاعات المحددة"""
        count = queryset.update(is_active=False)
        self.message_user(request, f'تم إلغاء تفعيل {count} قاعة')
    deactivate_rooms.short_description = "❌ إلغاء تفعيل القاعات"


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'email', 'get_subjects', 'phone', 'is_active', 'get_groups_count', 'created_at']
    list_filter = ['is_active', 'subjects', 'created_at']
    list_editable = ['is_active']  # تعديل سريع
    search_fields = ['full_name', 'email', 'phone']
    ordering = ['full_name']
    date_hierarchy = 'created_at'
    filter_horizontal = ['subjects']

    fieldsets = (
        ('معلومات المدرس', {
            'fields': ('full_name', 'email', 'phone', 'subjects', 'specialization', 'photo', 'hire_date', 'is_active')
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at', 'updated_at']

    actions = ['activate_teachers', 'deactivate_teachers']

    def get_queryset(self, request):
        """Prefetch subjects and annotate the group count (was N+1 per row)."""
        return super().get_queryset(request).prefetch_related('subjects').annotate(
            active_groups_count=Count(
                'groups', filter=Q(groups__is_active=True), distinct=True
            )
        )

    def get_subjects(self, obj):
        """عرض التخصصات"""
        return obj.get_subjects_display()
    get_subjects.short_description = 'التخصصات'

    @admin.display(description='عدد المجموعات', ordering='active_groups_count')
    def get_groups_count(self, obj):
        """عدد المجموعات للمدرس"""
        return f'{obj.active_groups_count} مجموعة'

    def activate_teachers(self, request, queryset):
        """تفعيل المدرسين المحددين"""
        count = queryset.update(is_active=True)
        self.message_user(request, f'تم تفعيل {count} مدرس/مدرسة')
    activate_teachers.short_description = "✅ تفعيل المدرسين"

    def deactivate_teachers(self, request, queryset):
        """إلغاء تفعيل المدرسين المحددين"""
        count = queryset.update(is_active=False)
        self.message_user(request, f'تم إلغاء تفعيل {count} مدرس/مدرسة')
    deactivate_teachers.short_description = "❌ إلغاء تفعيل المدرسين"


class GroupAdminForm(forms.ModelForm):
    """
    Admin form for ``Group`` with an **explicit** double-booking opt-in.

    The room-overlap rule used to be bypassed by matching the Arabic word
    'تعارض' inside ``str(exception)``: any rewording of the message silently
    turned "warn and save" into a hard 500, and the blanket
    ``skip_validation=True`` it then used also skipped the education
    stage/year check. Now the person saving has to tick a box, and only the
    overlap rule is relaxed.
    """

    allow_schedule_conflict = forms.BooleanField(
        required=False,
        label='السماح بتداخل مواعيد القاعة',
        help_text=(
            'فعّل هذا الخيار فقط إذا كنت تقصد حجز القاعة في وقت محجوز بالفعل. '
            'باقي قواعد التحقق (المرحلة والسنة الدراسية) تظل مطبّقة.'
        ),
    )

    class Meta:
        model = Group
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        # ``_post_clean`` runs right after this and calls ``instance.full_clean()``,
        # so the flag has to be on the instance before then.
        self.instance._skip_conflict_check = bool(
            cleaned_data.get('allow_schedule_conflict')
        )
        return cleaned_data


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    form = GroupAdminForm
    list_display = ['group_name', 'teacher', 'room', 'get_schedule', 'get_duration',
                    'gender_type', 'get_education', 'standard_fee', 'is_active', 'created_at']
    list_filter = ['schedule_day', 'is_active', 'teacher', 'room', 'gender_type',
                   'education_stage', 'education_year', 'created_at']
    list_editable = ['is_active']  # تعديل سريع
    search_fields = ['group_name', 'teacher__full_name', 'room__name']
    ordering = ['group_name']
    autocomplete_fields = ['teacher', 'room']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('معلومات المجموعة', {
            'fields': ('group_name', 'teacher', 'room', 'is_active')
        }),
        ('الجدول والمدة', {
            'fields': ('schedule_day', 'schedule_time', 'duration_minutes', 'allow_schedule_conflict'),
            'description': (
                '⚠️ النظام يمنع تداخل التوقيت تلقائياً (يسمح بنفس القاعة لمدرسين مختلفين بشرط عدم التداخل). '
                'المواعيد الكاملة للمجموعة تُدار من شاشة المجموعات (كل يوم بوقته).'
            )
        }),
        ('التصنيف (الجنس والمرحلة)', {
            'fields': ('gender_type', 'education_stage', 'education_year'),
        }),
        ('المالية', {
            'fields': ('standard_fee', 'center_percentage')
        }),
        ('معلومات النظام', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at']

    actions = ['activate_groups', 'deactivate_groups', 'clear_rooms']

    def get_queryset(self, request):
        """select_related + prefetch so the changelist is not N+1 per row."""
        return super().get_queryset(request).select_related(
            'teacher', 'room'
        ).prefetch_related('schedules')

    def get_duration(self, obj):
        """عرض المدة"""
        return obj.get_duration_display()
    get_duration.short_description = 'مدة الحصة'

    @admin.display(description='المواعيد')
    def get_schedule(self, obj):
        """كل مواعيد المجموعة (لا اليوم الأول فقط)"""
        return obj.get_schedule_display()

    def get_education(self, obj):
        """عرض المرحلة الدراسية"""
        parts = []
        if obj.education_stage:
            parts.append(obj.get_education_stage_display())
        if obj.education_year:
            parts.append(obj.get_education_year_display())
        return " - ".join(parts) if parts else "-"
    get_education.short_description = 'المرحلة'

    def save_model(self, request, obj, form, change):
        """
        حفظ المجموعة مع احترام خيار "السماح بتداخل مواعيد القاعة".

        No string matching on exception text: the conflicts are queried
        explicitly, and only the person who ticked the opt-in box can save on
        top of them. Every other validation rule still runs.
        """
        allow_conflict = bool(
            form.cleaned_data.get('allow_schedule_conflict')
            if hasattr(form, 'cleaned_data') else False
        )

        conflicts = obj.get_room_conflicts() if allow_conflict else []

        obj.save(skip_conflict_check=allow_conflict)

        if conflicts:
            other = conflicts[0]
            self.message_user(
                request,
                f'⚠️ تحذير: تم الحفظ مع تجاوز قاعدة منع التداخل الزمني. '
                f'القاعة "{obj.room.name if obj.room else "غير محددة"}" '
                f'محجوزة لمجموعة "{other.group_name}" يوم {other.get_day_display()} '
                f'الساعة {other.start_time.strftime("%I:%M %p")}!',
                level=messages.WARNING,
            )

    def activate_groups(self, request, queryset):
        """تفعيل المجموعات المحددة"""
        count = queryset.update(is_active=True)
        self.message_user(request, f'تم تفعيل {count} مجموعة')
    activate_groups.short_description = "✅ تفعيل المجموعات"

    def deactivate_groups(self, request, queryset):
        """إلغاء تفعيل المجموعات المحددة"""
        count = queryset.update(is_active=False)
        self.message_user(request, f'تم إلغاء تفعيل {count} مجموعة')
    deactivate_groups.short_description = "❌ إلغاء تفعيل المجموعات"

    def clear_rooms(self, request, queryset):
        """إزالة القاعات من المجموعات المحددة"""
        count = queryset.update(room=None)
        self.message_user(request, f'تم إزالة القاعة من {count} مجموعة')
    clear_rooms.short_description = "🏫 إزالة القاعات"
