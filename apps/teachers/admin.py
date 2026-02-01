from django.contrib import admin
from .models import Teacher, Group, Room


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

    def get_groups_count(self, obj):
        """عدد المجموعات في القاعة"""
        count = obj.groups.filter(is_active=True).count()
        return f'{count} مجموعة'
    get_groups_count.short_description = 'عدد المجموعات'

    def get_groups_list(self, obj):
        """قائمة المجموعات في القاعة"""
        groups = obj.groups.filter(is_active=True)
        if groups:
            return ", ".join([f"{g.group_name} ({g.schedule_day} {g.schedule_time})" for g in groups])
        return "لا توجد مجموعات"
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
    list_display = ['full_name', 'email', 'specialization', 'phone', 'is_active', 'get_groups_count', 'created_at']
    list_filter = ['is_active', 'specialization', 'created_at']
    list_editable = ['is_active']  # تعديل سريع
    search_fields = ['full_name', 'email', 'phone']
    ordering = ['full_name']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('معلومات المدرس', {
            'fields': ('full_name', 'email', 'phone', 'specialization', 'hire_date', 'is_active')
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at', 'updated_at']

    actions = ['activate_teachers', 'deactivate_teachers']

    def get_groups_count(self, obj):
        """عدد المجموعات للمدرس"""
        count = obj.groups.filter(is_active=True).count()
        return f'{count} مجموعة'
    get_groups_count.short_description = 'عدد المجموعات'

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


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['group_name', 'teacher', 'room', 'schedule_day', 'schedule_time', 'get_time_range', 'standard_fee', 'is_active', 'created_at']
    list_filter = ['schedule_day', 'is_active', 'teacher', 'room', 'created_at']
    list_editable = ['is_active']  # تعديل سريع
    search_fields = ['group_name', 'teacher__full_name', 'room__name']
    ordering = ['schedule_day', 'schedule_time']
    autocomplete_fields = ['teacher', 'room']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('معلومات المجموعة', {
            'fields': ('group_name', 'teacher', 'room', 'is_active')
        }),
        ('الجدول الزمني', {
            'fields': ('schedule_day', 'schedule_time', 'session_duration'),
            'description': '⚠️ النظام يمنع التعارضات تلقائياً (نفس القاعة + نفس اليوم + أوقات متداخلة). يجب وجود فاصل 15 دقيقة بين الحصص.'
        }),
        ('المالية', {
            'fields': ('standard_fee', 'center_percentage')
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at', 'updated_at', 'availability_status']

    actions = ['activate_groups', 'deactivate_groups', 'clear_rooms']
    
    class Media:
        css = {
            'all': ('css/room-scheduling-admin.css',)
        }
        js = ('js/room-scheduling-admin.js',)

    def save_model(self, request, obj, form, change):
        """
        تجاوز الـ validation للـ admin
        Admin له صلاحية تجاوز قاعدة منع التعارض
        """
        # التحقق من وجود تعارض
        try:
            obj.full_clean()
            has_conflict = False
        except Exception as e:
            if 'تعارض' in str(e) or 'conflict' in str(e).lower():
                has_conflict = True
            else:
                raise

        if has_conflict:
            # السؤال: هل تريد التجاوز؟
            # بما أن الـ admin panel لا يدعم dialogs، نحفظ مباشرة مع تحذير
            obj.save(skip_validation=True)
            self.message_user(
                request,
                f'⚠️ تحذير: تم الحفظ مع تجاوز قاعدة منع التعارض. '
                f'القاعة "{obj.room.name if obj.room else "غير محددة"}" '
                f'محجوزة لمجموعة أخرى في نفس الوقت!',
                level='WARNING'
            )
        else:
            # حفظ عادي
            obj.save()

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
    
    def get_time_range(self, obj):
        """عرض نطاق الوقت"""
        return obj.get_time_range_display()
    get_time_range.short_description = 'الوقت'
    
    def availability_status(self, obj):
        """حالة توفر القاعة (للعرض فقط)"""
        if not obj.room:
            return "⚪ لم يتم تحديد قاعة"
        
        from .services import RoomScheduleService
        
        conflict = RoomScheduleService.check_room_conflict(
            room=obj.room,
            day=obj.schedule_day,
            start_time=obj.schedule_time,
            duration=obj.session_duration,
            exclude_group_id=obj.pk
        )
        
        if conflict:
            return f'⛔ {conflict["message_ar"]}'
        
        return '✅ القاعة متاحة'
    availability_status.short_description = 'حالة التوفر'
    
    def get_form(self, request, obj=None, **kwargs):
        """تخصيص النموذج لإضافة حقول إضافية"""
        form = super().get_form(request, obj, **kwargs)
        
        # إضافة فئة CSS للحقول التي تحتاج فحص تعارض
        if form.base_fields.get('room'):
            form.base_fields['room'].widget.attrs.update({'class': 'conflict-check-room'})
        if form.base_fields.get('schedule_day'):
            form.base_fields['schedule_day'].widget.attrs.update({'class': 'conflict-check-day'})
        if form.base_fields.get('schedule_time'):
            form.base_fields['schedule_time'].widget.attrs.update({'class': 'conflict-check-time'})
        if form.base_fields.get('session_duration'):
            form.base_fields['session_duration'].widget.attrs.update({'class': 'conflict-check-duration'})
        
        return form
    
    def response_add(self, request, obj, post_url_continue=None):
        """معالجة الاستجابة بعد الإضافة"""
        # التحقق من وجود تعارضات تم تخطيها
        if hasattr(obj, '_skipped_conflict'):
            self.message_user(
                request,
                '⚠️ تم حفظ المجموعة مع تجاوز قاعدة منع التعارض',
                level='WARNING'
            )
        return super().response_add(request, obj, post_url_continue)
    
    def response_change(self, request, obj):
        """معالجة الاستجابة بعد التعديل"""
        # التحقق من وجود تعارضات تم تخطيها
        if hasattr(obj, '_skipped_conflict'):
            self.message_user(
                request,
                '⚠️ تم حفظ التعديلات مع تجاوز قاعدة منع التعارض',
                level='WARNING'
            )
        return super().response_change(request, obj)


@admin.register(Room)
class RoomAdminWithSchedule(RoomAdmin):
    """توسيع إدارة القاعات مع عرض الجدول"""
    
    list_display = ['name', 'capacity', 'is_active', 'get_utilization', 'get_groups_count', 'created_at']
    
    def get_utilization(self, obj):
        """عرض نسبة الاستخدام"""
        from .services import RoomScheduleService
        
        utilization = RoomScheduleService.calculate_room_utilization(obj)
        percentage = utilization['utilization_percentage']
        
        # تلوين النسبة
        if percentage >= 80:
            color = 'green'
        elif percentage >= 50:
            color = 'orange'
        else:
            color = 'red'
        
        return f'<span style="color: {color}; font-weight: bold;">{percentage}%</span>'
    get_utilization.short_description = 'نسبة الاستخدام'
    get_utilization.allow_tags = True
    
    def get_schedule(self, obj):
        """عرض جدول القاعة"""
        from .services import RoomScheduleService
        
        schedule = RoomScheduleService.get_room_schedule(obj)
        
        html = '<div style="direction: rtl;">'
        for day, sessions in schedule.items():
            if sessions:
                html += f'<strong>{day}:</strong><ul>'
                for session in sessions:
                    html += f'<li>{session["start"]} - {session["end"]}: {session["group_name"]}</li>'
                html += '</ul>'
        html += '</div>'
        
        return html
    get_schedule.short_description = 'الجدول الأسبوعي'
    
    readonly_fields = ['created_at', 'updated_at', 'get_groups_list', 'get_schedule']
    
    fieldsets = (
        ('معلومات القاعة', {
            'fields': ('name', 'capacity', 'is_active')
        }),
        ('إحصائيات الاستخدام', {
            'fields': ('get_schedule',),
            'classes': ('collapse',)
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
