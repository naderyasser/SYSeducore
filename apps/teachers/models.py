from django.db import models
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from datetime import datetime, timedelta
from apps.core.models import SoftDeleteModel


#: Week days in the order the centre uses them (Saturday is the first school day).
WEEK_DAYS = [
    'Saturday', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday',
]

#: Arabic labels for :data:`WEEK_DAYS`.
WEEK_DAYS_AR = {
    'Saturday': 'السبت',
    'Sunday': 'الأحد',
    'Monday': 'الاثنين',
    'Tuesday': 'الثلاثاء',
    'Wednesday': 'الأربعاء',
    'Thursday': 'الخميس',
    'Friday': 'الجمعة',
}


class Room(SoftDeleteModel):
    """
    Room model for managing classrooms.
    موديل القاعات الدراسية
    """
    room_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True, verbose_name="اسم القاعة")
    capacity = models.PositiveIntegerField(verbose_name="السعة القصوى")

    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rooms'
        verbose_name = 'قاعة'
        verbose_name_plural = 'القاعات'
        ordering = ['name']

    def __str__(self):
        return self.name


class Subject(SoftDeleteModel):
    """
    Subject model for managing subjects/specializations.
    موديل المواد الدراسية

    Soft-deletable like every other entity in the system: deleting a subject
    used to be a hard ``DELETE`` that silently dropped the ``Teacher.subjects``
    rows of every teacher that taught it, with no way back (DATA-26).
    """
    EDUCATION_STAGE_CHOICES = [
        ('primary', 'ابتدائي'),
        ('preparatory', 'إعدادي'),
        ('secondary', 'ثانوي'),
    ]

    name = models.CharField(max_length=100, verbose_name="اسم المادة")
    education_stage = models.CharField(
        max_length=20,
        choices=EDUCATION_STAGE_CHOICES,
        blank=True,
        default='',
        verbose_name="المرحلة الدراسية"
    )

    class Meta:
        db_table = 'subjects'
        verbose_name = 'مادة دراسية'
        verbose_name_plural = 'المواد الدراسية'
        unique_together = [('name', 'education_stage')]
        ordering = ['name']

    def __str__(self):
        return self.name


class Teacher(SoftDeleteModel):
    """
    Teacher model for managing teachers.
    """
    teacher_id = models.AutoField(primary_key=True)
    full_name = models.CharField(max_length=255, verbose_name="اسم المدرس")
    phone = models.CharField(max_length=17, verbose_name="رقم الهاتف")
    email = models.EmailField(
        blank=True,
        null=True,
        unique=True,
        verbose_name="البريد الإلكتروني",
        help_text="حقل اختياري"
    )

    # Multi-select subjects through M2M
    subjects = models.ManyToManyField(
        Subject,
        blank=True,
        related_name='teachers',
        verbose_name="التخصصات / المواد"
    )
    # Keep legacy field for backward compat (will be migrated)
    specialization = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="التخصص (قديم)"
    )

    # Profile photo - required for student card back
    photo = models.ImageField(
        upload_to='teachers/photos/',
        blank=True,
        null=True,
        verbose_name="الصورة الشخصية",
        help_text="ضرورية لطباعة ظهر كارنيه الطالب"
    )

    hire_date = models.DateField(verbose_name="تاريخ التعيين")

    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'teachers'
        verbose_name = 'مدرس'
        verbose_name_plural = 'المدرسين'
        ordering = ['full_name']

    def __str__(self):
        return self.full_name

    def get_subjects_display(self):
        """عرض المواد مفصولة بفاصلة"""
        subjects = self.subjects.all()
        if subjects:
            return " ، ".join([s.name for s in subjects])
        return self.specialization or "-"


class ScheduleEntry:
    """
    A single weekly session — one group meeting on one day.

    ``GroupSchedule`` is the single source of truth for the weekly timetable
    (a group may meet on several days, each with its own start time and
    duration). ``ScheduleEntry`` is a lightweight read-only view over one of
    those rows — or, for a legacy group that has no ``GroupSchedule`` rows at
    all, over the group's legacy ``schedule_day`` / ``schedule_time`` /
    ``duration_minutes`` fields.

    It deliberately duck-types the attributes callers used to read straight
    off ``Group`` (``group_id``, ``group_name``, ``teacher``, ``room``,
    ``schedule_time``, ``get_end_time()``, ``get_duration_display()``) so
    templates and APIs can iterate sessions instead of groups without any
    other change.
    """

    __slots__ = ('group', 'day_of_week', 'start_time', 'duration', 'schedule_id')

    def __init__(self, group, day_of_week, start_time, duration, schedule_id=None):
        self.group = group
        self.day_of_week = day_of_week
        self.start_time = start_time
        self.duration = int(duration or 0)
        self.schedule_id = schedule_id

    # -- identity ---------------------------------------------------------
    def __repr__(self):  # pragma: no cover - debugging aid
        return (
            f'<ScheduleEntry {self.group_name} {self.day_of_week} '
            f'{self.start_time}>'
        )

    def __eq__(self, other):
        if not isinstance(other, ScheduleEntry):
            return NotImplemented
        return (
            self.group_id == other.group_id
            and self.day_of_week == other.day_of_week
            and self.start_time == other.start_time
        )

    def __hash__(self):
        return hash((self.group_id, self.day_of_week, self.start_time))

    # -- Group compatibility aliases --------------------------------------
    @property
    def group_id(self):
        return self.group.pk

    @property
    def group_name(self):
        return self.group.group_name

    @property
    def teacher(self):
        return self.group.teacher

    @property
    def room(self):
        return self.group.room

    @property
    def standard_fee(self):
        return self.group.standard_fee

    @property
    def schedule_time(self):
        """Alias kept so templates written against ``Group`` keep working."""
        return self.start_time

    @property
    def duration_minutes(self):
        return self.duration

    @property
    def schedule_day(self):
        return self.day_of_week

    # -- time helpers -----------------------------------------------------
    def get_start_datetime(self, reference_date=None):
        base = reference_date or datetime.today()
        return datetime.combine(base, self.start_time)

    def get_end_datetime(self, reference_date=None):
        return self.get_start_datetime(reference_date) + timedelta(minutes=self.duration)

    def get_end_time(self):
        """وقت نهاية الحصة"""
        return self.get_end_datetime().time()

    def get_day_display(self):
        return WEEK_DAYS_AR.get(self.day_of_week, self.day_of_week)

    # kept for parity with ``Group.get_schedule_day_display``
    get_schedule_day_display = get_day_display

    def get_duration_display(self):
        hours = self.duration // 60
        mins = self.duration % 60
        if hours and mins:
            return f"{hours} ساعة و {mins} دقيقة"
        elif hours:
            return f"{hours} ساعة" if hours == 1 else f"{hours} ساعات"
        return f"{mins} دقيقة"

    def overlaps(self, start_dt, end_dt):
        """True when this session overlaps the ``[start_dt, end_dt)`` window."""
        own_start = self.get_start_datetime()
        own_end = own_start + timedelta(minutes=self.duration)
        return start_dt < own_end and own_start < end_dt


class Group(SoftDeleteModel):
    """
    Group model for managing student groups.
    يدعم مدة الحصة + منع التعارض الذكي (تداخل الوقت) + تصنيف الجنس والمرحلة
    """
    DAYS_CHOICES = [
        ('Saturday', 'السبت'),
        ('Sunday', 'الأحد'),
        ('Monday', 'الاثنين'),
        ('Tuesday', 'الثلاثاء'),
        ('Wednesday', 'الأربعاء'),
        ('Thursday', 'الخميس'),
        ('Friday', 'الجمعة'),
    ]

    GENDER_CHOICES = [
        ('male', 'بنين فقط'),
        ('female', 'بنات فقط'),
        ('mixed', 'مختلط'),
    ]

    EDUCATION_STAGE_CHOICES = [
        ('primary', 'ابتدائي'),
        ('preparatory', 'إعدادي'),
        ('secondary', 'ثانوي'),
    ]

    EDUCATION_YEAR_CHOICES = [
        ('1', 'الصف الأول'),
        ('2', 'الصف الثاني'),
        ('3', 'الصف الثالث'),
        ('4', 'الصف الرابع'),
        ('5', 'الصف الخامس'),
        ('6', 'الصف السادس'),
    ]

    group_id = models.AutoField(primary_key=True)
    group_name = models.CharField(max_length=100, verbose_name="اسم المجموعة")
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.PROTECT,
        related_name='groups',
        verbose_name="المدرس"
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.PROTECT,
        related_name='groups',
        verbose_name="القاعة",
        null=True,
        blank=True
    )

    schedule_day = models.CharField(
        max_length=10,
        choices=DAYS_CHOICES,
        verbose_name="يوم الحصة"
    )
    schedule_time = models.TimeField(verbose_name="وقت بداية الحصة")

    # Duration field - مدة الحصة بالدقائق
    duration_minutes = models.PositiveIntegerField(
        default=120,
        verbose_name="مدة الحصة (بالدقائق)",
        help_text="مدة الحصة بالدقائق (مثال: 120 = ساعتين)"
    )

    # Gender classification - تصنيف الجنس
    gender_type = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
        default='mixed',
        verbose_name="نوع المجموعة (الجنس)"
    )

    # Education stage and year - المرحلة والسنة الدراسية
    education_stage = models.CharField(
        max_length=20,
        choices=EDUCATION_STAGE_CHOICES,
        blank=True,
        verbose_name="المرحلة الدراسية"
    )
    education_year = models.CharField(
        max_length=5,
        choices=EDUCATION_YEAR_CHOICES,
        blank=True,
        verbose_name="السنة الدراسية"
    )

    standard_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="السعر القياسي"
    )
    center_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=30.00,
        verbose_name="نسبة السنتر %"
    )
    sessions_per_month = models.PositiveIntegerField(
        default=4,
        verbose_name="عدد الحصص في الشهر"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'groups'
        verbose_name = 'مجموعة'
        verbose_name_plural = 'المجموعات'
        # Remove old unique constraint - replaced by smart overlap check

    def get_end_time(self):
        """حساب وقت نهاية الحصة بناءً على وقت البداية والمدة"""
        start_dt = datetime.combine(datetime.today(), self.schedule_time)
        end_dt = start_dt + timedelta(minutes=self.duration_minutes)
        return end_dt.time()

    def clean(self):
        """
        التحقق من عدم وجود تداخل في جدول القاعات (Smart Overlap Check)
        يسمح بنفس القاعة لمدرسين مختلفين بشرط عدم تداخل التوقيت

        المنطق: إذا حجز مدرس القاعة من 11:00 إلى 1:00،
        يمكن لمدرس آخر الحجز فيها بدءاً من 1:00،
        ولكن يمنع الحجز الساعة 12:00

        The overlap check consults :class:`GroupSchedule` (the single source of
        truth) for every other group, so a clash on the *second* or *third* day
        of a multi-day group is caught too — reading the legacy
        ``schedule_day`` column only ever saw the first day.

        Conflicts are reported under ``NON_FIELD_ERRORS`` rather than
        ``schedule_time``: ``schedule_time`` is not a field of ``GroupForm``
        (nor of the admin's list-editable form), and ``BaseForm.add_error``
        raises ``ValueError`` for an error keyed on a field the form does not
        have — which turned a validation failure into a 500.
        """
        super().clean()

        # التحقق من صحة المرحلة والسنة الدراسية
        STAGE_YEAR_MAP = {
            'primary': ['1', '2', '3', '4', '5', '6'],
            'preparatory': ['1', '2', '3'],
            'secondary': ['1', '2', '3'],
        }
        if self.education_stage and self.education_year:
            valid_years = STAGE_YEAR_MAP.get(self.education_stage, [])
            if self.education_year not in valid_years:
                stage_display = dict(self.EDUCATION_STAGE_CHOICES).get(self.education_stage, self.education_stage)
                raise ValidationError({
                    'education_year': f'الصف {self.education_year} غير متاح للمرحلة {stage_display}'
                })

        # ``skip_conflict_check`` is an explicit, per-save opt-in (used by the
        # admin) — it never disables the stage/year check above.
        if getattr(self, '_skip_conflict_check', False):
            return

        conflicts = self.get_room_conflicts()
        if conflicts:
            raise ValidationError({NON_FIELD_ERRORS: [build_conflict_message(self.room, conflicts[0])]})

    def get_room_conflicts(self):
        """
        Room bookings that clash with this group's own sessions.

        Returns a list of :class:`ScheduleEntry`. Empty means the group can be
        saved. Callers (the admin) can test this explicitly instead of
        pattern-matching Arabic text out of an exception message.
        """
        if not self.room:
            return []

        conflicts = []
        for entry in self.get_schedule_entries():
            conflicts.extend(
                find_room_conflicts(
                    self.room,
                    entry.day_of_week,
                    entry.start_time,
                    entry.duration,
                    exclude_group_pk=self.pk,
                )
            )
        return conflicts

    #: Saving any of these requires the model-level validation to run again.
    #: A partial ``save(update_fields=...)`` that touches nothing else (the
    #: soft-delete write, an ``is_active`` toggle…) can safely skip it — the
    #: stored values were validated when they were written.
    VALIDATED_FIELDS = frozenset({
        'room', 'room_id', 'schedule_day', 'schedule_time', 'duration_minutes',
        'education_stage', 'education_year', 'is_active', 'group_name',
        'teacher', 'teacher_id', 'standard_fee', 'center_percentage',
        'sessions_per_month', 'gender_type',
    })

    def save(self, *args, skip_validation=False, skip_conflict_check=False, **kwargs):
        """
        تنفيذ التحقق قبل الحفظ

        Args:
            skip_validation: يتخطى كل الـ validation (للاستخدام الداخلي فقط)
            skip_conflict_check: يتخطى فحص تعارض القاعة فقط — بقية التحقق
                (المرحلة/السنة الدراسية، الحقول المطلوبة) يظل يعمل.
                هذا هو الخيار الذي يستخدمه الـ admin عند الحجز المتعمد.
        """
        update_fields = kwargs.get('update_fields')
        needs_validation = not skip_validation
        if needs_validation and update_fields is not None:
            needs_validation = bool(set(update_fields) & self.VALIDATED_FIELDS)

        if needs_validation:
            previous = getattr(self, '_skip_conflict_check', False)
            self._skip_conflict_check = skip_conflict_check or previous
            try:
                self.full_clean()
            finally:
                self._skip_conflict_check = previous
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.group_name} - {self.teacher.full_name}"

    def get_duration_display(self):
        """عرض المدة بشكل مقروء"""
        hours = self.duration_minutes // 60
        mins = self.duration_minutes % 60
        if hours and mins:
            return f"{hours} ساعة و {mins} دقيقة"
        elif hours:
            return f"{hours} ساعة" if hours == 1 else f"{hours} ساعات"
        else:
            return f"{mins} دقيقة"

    def get_schedules(self):
        """الحصول على جداول المجموعة (صفوف GroupSchedule الخام)"""
        return self.schedules.all().order_by('day_of_week')

    def get_schedule_entries(self):
        """
        كل مواعيد المجموعة في الأسبوع — المصدر الوحيد للحقيقة.

        Returns a list of :class:`ScheduleEntry`, one per day the group meets,
        ordered by day then time. Falls back to the legacy
        ``schedule_day``/``schedule_time``/``duration_minutes`` fields when the
        group has no ``GroupSchedule`` rows yet, so old data keeps working.
        """
        return group_schedule_entries(self)

    def get_schedule_for_day(self, day_name):
        """
        موعد المجموعة في يوم معيّن (أو ``None``).

        Returns a :class:`ScheduleEntry` — it exposes ``start_time``,
        ``duration`` and ``get_end_time()`` exactly like ``GroupSchedule`` does,
        and additionally covers legacy groups that have no ``GroupSchedule``
        rows.
        """
        for entry in self.get_schedule_entries():
            if entry.day_of_week == day_name:
                return entry
        return None

    def get_schedule_days(self):
        """أسماء أيام المجموعة"""
        return [entry.day_of_week for entry in self.get_schedule_entries()]

    def get_schedule_display(self):
        """عرض مواعيد المجموعة بالعربية"""
        return " ، ".join(
            f"{entry.get_day_display()} {entry.start_time.strftime('%I:%M %p')}"
            for entry in self.get_schedule_entries()
        ) or "-"

    def sync_legacy_schedule_fields(self, schedule_data=None):
        """
        Keep the legacy ``schedule_day``/``schedule_time``/``duration_minutes``
        columns pointing at the group's first session.

        They are still read by consumers outside this app, so they must stay
        populated — but ``GroupSchedule`` is what actually describes the week.
        Does not save; the caller decides when to write.
        """
        if schedule_data:
            first = schedule_data[0]
            self.schedule_day = first['day']
            self.schedule_time = first['time']
            self.duration_minutes = int(
                first.get('duration') or self.duration_minutes or 120
            )
            return self

        entries = self.get_schedule_entries()
        if entries:
            first = entries[0]
            self.schedule_day = first.day_of_week
            self.schedule_time = first.start_time
            self.duration_minutes = first.duration
        return self


class GroupSchedule(models.Model):
    """
    جدول المجموعة - يوم بيوم مع وقت مستقل لكل يوم
    يسمح بأن يكون لكل يوم في المجموعة وقت بداية ومدة مختلفة
    """
    DAYS_CHOICES = Group.DAYS_CHOICES

    schedule_id = models.AutoField(primary_key=True)
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='schedules',
        verbose_name="المجموعة"
    )
    day_of_week = models.CharField(
        max_length=10,
        choices=DAYS_CHOICES,
        verbose_name="يوم الحصة"
    )
    start_time = models.TimeField(verbose_name="وقت بداية الحصة")
    duration = models.PositiveIntegerField(
        default=120,
        verbose_name="مدة الحصة (بالدقائق)",
        help_text="مدة الحصة بالدقائق"
    )

    class Meta:
        db_table = 'group_schedules'
        verbose_name = 'جدول مجموعة'
        verbose_name_plural = 'جداول المجموعات'
        unique_together = ['group', 'day_of_week']
        ordering = ['day_of_week', 'start_time']

    def __str__(self):
        return f"{self.group.group_name} - {self.get_day_of_week_display()} {self.start_time.strftime('%I:%M %p')}"

    def get_end_time(self):
        """حساب وقت نهاية الحصة"""
        start_dt = datetime.combine(datetime.today(), self.start_time)
        end_dt = start_dt + timedelta(minutes=self.duration)
        return end_dt.time()

    def clean(self):
        """التحقق من عدم تداخل القاعة في نفس اليوم والوقت"""
        super().clean()

        group = self.group if self.group_id else None
        if not (group and group.room and self.day_of_week and self.start_time):
            return

        conflicts = find_room_conflicts(
            group.room,
            self.day_of_week,
            self.start_time,
            self.duration,
            exclude_group_pk=group.pk,
            exclude_schedule_pk=self.pk,
        )
        if conflicts:
            raise ValidationError({
                'start_time': build_conflict_message(group.room, conflicts[0])
            })


# ---------------------------------------------------------------------------
# Schedule queries — GroupSchedule is the single source of truth
# ---------------------------------------------------------------------------

def build_conflict_message(room, entry):
    """رسالة تعارض موحّدة لكل أماكن التحقق"""
    end = entry.get_end_time().strftime('%I:%M %p')
    return (
        f'تعارض في الجدول: القاعة "{room.name}" محجوزة لمجموعة '
        f'"{entry.group_name}" يوم {entry.get_day_display()} '
        f'من {entry.start_time.strftime("%I:%M %p")} إلى {end}. '
        f'يمكنك الحجز بدءاً من {end}'
    )


def group_schedule_entries(group):
    """
    All weekly sessions of one group as :class:`ScheduleEntry` objects.

    ``GroupSchedule`` rows win; a group with no rows at all falls back to its
    legacy ``schedule_day``/``schedule_time``/``duration_minutes`` fields.
    Uses ``group.schedules`` so a ``prefetch_related('schedules')`` on the
    caller's queryset costs no extra query.
    """
    entries = []
    if group.pk is not None:
        # ``group.schedules`` needs a primary key; an unsaved group being
        # validated has only its legacy fields.
        entries = [
            ScheduleEntry(group, s.day_of_week, s.start_time, s.duration, s.pk)
            for s in group.schedules.all()
        ]
    if not entries and group.schedule_day and group.schedule_time:
        entries.append(
            ScheduleEntry(
                group,
                group.schedule_day,
                group.schedule_time,
                group.duration_minutes or 120,
            )
        )
    entries.sort(key=lambda e: (_day_order(e.day_of_week), e.start_time))
    return entries


def _day_order(day_name):
    try:
        return WEEK_DAYS.index(day_name)
    except ValueError:
        return len(WEEK_DAYS)


def room_schedule_entries(room, day_of_week=None, exclude_group_pk=None,
                          groups=None, start_before=None):
    """
    Every session held in ``room`` — optionally restricted to one day.

    Two queries regardless of how many groups use the room: one over
    ``GroupSchedule`` and one over the legacy groups that have no
    ``GroupSchedule`` rows at all.

    ``groups`` may be a pre-fetched iterable of the room's active groups; when
    given it is used verbatim (already annotated/`select_related`) instead of
    re-querying, which is what the room views do.

    ``start_before`` narrows the query to sessions starting before that time —
    used by the overlap check so a busy room does not have to be walked in
    Python on every ``Group.save()``.
    """
    if room is None:
        return []

    if groups is not None:
        entries = []
        for group in groups:
            if exclude_group_pk is not None and group.pk == exclude_group_pk:
                continue
            for entry in group_schedule_entries(group):
                if day_of_week is not None and entry.day_of_week != day_of_week:
                    continue
                if start_before is not None and entry.start_time >= start_before:
                    continue
                entries.append(entry)
        entries.sort(key=lambda e: (_day_order(e.day_of_week), e.start_time))
        return entries

    schedules = GroupSchedule.objects.filter(
        group__room=room,
        group__is_active=True,
        group__deleted_at__isnull=True,
    ).select_related('group', 'group__teacher', 'group__room')
    legacy = Group.objects.filter(
        room=room,
        is_active=True,
        schedules__isnull=True,
    ).select_related('teacher', 'room')

    if day_of_week is not None:
        schedules = schedules.filter(day_of_week=day_of_week)
        legacy = legacy.filter(schedule_day=day_of_week)
    if exclude_group_pk is not None:
        schedules = schedules.exclude(group_id=exclude_group_pk)
        legacy = legacy.exclude(pk=exclude_group_pk)
    if start_before is not None:
        schedules = schedules.filter(start_time__lt=start_before)
        legacy = legacy.filter(schedule_time__lt=start_before)

    entries = [
        ScheduleEntry(s.group, s.day_of_week, s.start_time, s.duration, s.pk)
        for s in schedules
    ]
    entries.extend(
        ScheduleEntry(g, g.schedule_day, g.schedule_time, g.duration_minutes or 120)
        for g in legacy
        if g.schedule_day and g.schedule_time
    )
    entries.sort(key=lambda e: (_day_order(e.day_of_week), e.start_time))
    return entries


def room_week_entries(room, groups=None, exclude_group_pk=None):
    """
    ``{day_name: [ScheduleEntry, ...]}`` for every day ``room`` is in use.
    Days with no sessions are omitted; each day's list is ordered by time.
    """
    week = {}
    for entry in room_schedule_entries(
        room, exclude_group_pk=exclude_group_pk, groups=groups
    ):
        week.setdefault(entry.day_of_week, []).append(entry)
    return {day: week[day] for day in WEEK_DAYS if day in week}


def find_room_conflicts(room, day_of_week, start_time, duration,
                        exclude_group_pk=None, exclude_schedule_pk=None):
    """
    Sessions already booked in ``room`` on ``day_of_week`` that overlap
    ``[start_time, start_time + duration)``.

    Returns a list of :class:`ScheduleEntry` (empty = the slot is free).
    This is the one overlap implementation used by ``Group.clean``,
    ``GroupSchedule.clean`` and the availability API.
    """
    if not (room and day_of_week and start_time):
        return []

    new_start = datetime.combine(datetime.today(), start_time)
    new_end = new_start + timedelta(minutes=int(duration or 0))

    # Only sessions starting before this one ends can overlap it — unless the
    # session runs past midnight, in which case every start time qualifies.
    start_before = new_end.time() if new_end.date() == new_start.date() else None

    candidates = room_schedule_entries(
        room,
        day_of_week=day_of_week,
        exclude_group_pk=exclude_group_pk,
        start_before=start_before,
    )
    return [
        entry for entry in candidates
        if entry.schedule_id is None or entry.schedule_id != exclude_schedule_pk
        if entry.overlaps(new_start, new_end)
    ]
