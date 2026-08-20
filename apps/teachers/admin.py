from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q

from .models import Teacher, Group, GroupSchedule, Room, Subject


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'education_stage', 'get_teachers_count']
    list_filter = ['education_stage']
    search_fields = ['name']
    ordering = ['name']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            teachers_count=Count(
                'teachers',
                filter=Q(teachers__is_active=True, teachers__deleted_at__isnull=True),
                distinct=True,
            )
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
                'schedule_entries__group',
                filter=Q(schedule_entries__group__is_active=True),
                distinct=True,
            )
        )

    @admin.display(description='عدد المجموعات', ordering='active_groups_count')
    def get_groups_count(self, obj):
        """عدد المجموعات في القاعة"""
        return f'{obj.active_groups_count} مجموعة'

    def get_groups_list(self, obj):
        """قائمة المجموعات في القاعة"""
        groups = (
            Group.objects.filter(schedules__room=obj, is_active=True)
            .distinct()
            .prefetch_related('schedules__room')
        )
        parts = []
        for group in groups:
            schedule = " ، ".join(
                f"{entry.get_day_display()} {entry.start_time.strftime('%I:%M %p')}"
                f" - {entry.get_end_time().strftime('%I:%M %p')}"
                for entry in group.get_schedule_entries()
                if entry.room and entry.room.pk == obj.pk
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

    ``room`` is not a ``Group`` field (rooms live on ``GroupSchedule``, one
    per session) — it exists here purely so this quick admin screen's single
    day/time pair (see the "الجدول والمدة" fieldset) still has a room to
    conflict-check and persist against. ``GroupAdmin.save_model`` upserts the
    matching ``GroupSchedule`` row for ``schedule_day`` only; it never
    touches the group's other days.
    """

    room = forms.ModelChoiceField(
        queryset=Room.objects.filter(is_active=True),
        required=False,
        label='القاعة (اليوم الأول فقط)',
        help_text='قاعة الموعد في حقل "يوم الحصة" أدناه فقط — بقية أيام المجموعة تُدار من شاشة المجموعات.',
    )
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            entry = self.instance.get_schedule_for_day(self.instance.schedule_day)
            if entry and entry.room:
                self.fields['room'].initial = entry.room.pk

    def clean(self):
        cleaned_data = super().clean()
        day = cleaned_data.get('schedule_day')
        start_time = cleaned_data.get('schedule_time')
        # ``_post_clean`` runs right after this and calls ``instance.full_clean()``,
        # so both flags have to be on the instance before then.
        self.instance._skip_conflict_check = bool(
            cleaned_data.get('allow_schedule_conflict')
        )
        if day and start_time:
            self.instance._pending_schedules = [{
                'day': day,
                'time': start_time,
                'duration': cleaned_data.get('duration_minutes') or self.instance.duration_minutes,
                'room': cleaned_data.get('room'),
            }]
        return cleaned_data


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    form = GroupAdminForm
    list_display = ['group_name', 'teacher', 'get_rooms', 'get_schedule', 'get_duration',
                    'gender_type', 'get_education', 'standard_fee', 'is_active', 'created_at']
    list_filter = ['schedule_day', 'is_active', 'teacher', 'schedules__room', 'gender_type',
                   'education_stage', 'education_year', 'created_at']
    list_editable = ['is_active']  # تعديل سريع
    search_fields = ['group_name', 'teacher__full_name', 'schedules__room__name']
    ordering = ['group_name']
    autocomplete_fields = ['teacher']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('معلومات المجموعة', {
            'fields': ('group_name', 'teacher', 'is_active')
        }),
        ('الجدول والمدة', {
            'fields': ('schedule_day', 'schedule_time', 'duration_minutes', 'room', 'allow_schedule_conflict'),
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

    actions = ['activate_groups', 'deactivate_groups']

    def get_queryset(self, request):
        """select_related + prefetch so the changelist is not N+1 per row."""
        return super().get_queryset(request).select_related(
            'teacher'
        ).prefetch_related('schedules__room')

    @admin.display(description='القاعة')
    def get_rooms(self, obj):
        """قاعة/قاعات المجموعة (تفصيل باليوم لو اختلفت القاعة بين الأيام)"""
        return obj.get_rooms_display()

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

        # Keep the real schedule truth (GroupSchedule) in sync with this
        # screen's single day/time/room fields — upsert on (group, day) only,
        # so a group's other days (managed from the Groups screen) are left
        # untouched.
        if obj.schedule_day and obj.schedule_time:
            GroupSchedule.objects.update_or_create(
                group=obj, day_of_week=obj.schedule_day,
                defaults={
                    'start_time': obj.schedule_time,
                    'duration': obj.duration_minutes,
                    'room': form.cleaned_data.get('room') if hasattr(form, 'cleaned_data') else None,
                },
            )

        if conflicts:
            other = conflicts[0]
            self.message_user(
                request,
                f'⚠️ تحذير: تم الحفظ مع تجاوز قاعدة منع التداخل الزمني. '
                f'القاعة "{other.room.name if other.room else "غير محددة"}" '
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
