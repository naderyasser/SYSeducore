from decimal import Decimal

from django import forms
from django.db import transaction
from django.db.models import Q

from .models import MAX_SESSIONS_PER_CYCLE, Teacher, Group, Room, Subject, GroupSchedule


class TeacherForm(forms.ModelForm):
    """
    Form للمدرس مع الحقول الجديدة:
    - البريد الإلكتروني اختياري
    - التخصصات متعددة الاختيار
    - الصورة الشخصية
    """
    # Multi-select subjects field
    subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'form-check-input',
        }),
        label="التخصصات / المواد",
        help_text="اختر مادة أو أكثر"
    )

    class Meta:
        model = Teacher
        fields = ['full_name', 'phone', 'email', 'subjects', 'specialization', 'photo', 'hire_date', 'is_active']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المدرس'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '01xxxxxxxxx'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'example@email.com (اختياري)'}),
            'specialization': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'التخصص (نص حر)'}),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'hire_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = False
        self.fields['specialization'].required = False
        if self.instance and self.instance.pk:
            self.fields['subjects'].initial = self.instance.subjects.all()

    def clean_email(self):
        """
        البريد الإلكتروني حقل اختياري.

        ``Teacher.email`` is ``unique=True``, and Django form fields clean an
        empty input to ``''`` — not ``None``. Storing ``''`` means the *second*
        teacher left without an email collides with the first and the save dies
        with an ``IntegrityError``. Normalise blank to ``NULL``, which a unique
        index does not constrain.
        """
        email = (self.cleaned_data.get('email') or '').strip()
        if not email:
            return None

        # ``Teacher.objects`` hides soft-deleted rows, so ModelForm's own
        # uniqueness check cannot see a deleted teacher still holding this
        # address — the save would then fail with a raw IntegrityError.
        clash = Teacher.all_objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        clash = clash.first()
        if clash is not None:
            if clash.deleted_at is not None:
                raise forms.ValidationError(
                    'هذا البريد الإلكتروني مستخدم بواسطة مدرس محذوف موجود في سلة المهملات'
                )
            raise forms.ValidationError('هذا البريد الإلكتروني مستخدم بالفعل')
        return email

    def save(self, commit=True):
        teacher = super().save(commit=commit)
        if commit:
            teacher.subjects.set(self.cleaned_data.get('subjects', []))
        return teacher


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['name', 'capacity', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم القاعة'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'السعة القصوى'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_name(self):
        """
        ``Room.name`` هو unique=True على مستوى القاعدة.

        ``Room.objects`` يخفي القاعات المحذوفة (soft-delete)، فلا يرى تحقق
        ``ModelForm`` من التفرد قاعة موجودة في سلة المهملات بنفس الاسم —
        والحفظ كان ينفجر بـ ``IntegrityError`` خام. نفس النمط المستخدم في
        ``TeacherForm.clean_email``.
        """
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            return name

        clash = Room.all_objects.filter(name__iexact=name)
        if self.instance and self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        clash = clash.first()
        if clash is not None:
            if clash.deleted_at is not None:
                raise forms.ValidationError(
                    'هذا الاسم مستخدم بواسطة قاعة محذوفة موجودة في سلة المهملات'
                )
            raise forms.ValidationError('هذه القاعة موجودة بالفعل')
        return name


class GroupForm(forms.ModelForm):
    """
    Form للمجموعة مع دعم الجداول المتعددة
    """

    class Meta:
        model = Group
        fields = [
            'group_name', 'teacher',
            'duration_minutes', 'gender_type', 'education_stage', 'education_year',
            'standard_fee', 'center_percentage', 'sessions_per_month', 'is_active'
        ]
        widgets = {
            'group_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المجموعة'}),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'duration_minutes': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '120',
                'min': '30',
                'step': '15',
            }),
            'gender_type': forms.Select(attrs={'class': 'form-select'}),
            'education_stage': forms.Select(attrs={'class': 'form-select'}),
            'education_year': forms.Select(attrs={'class': 'form-select'}),
            'standard_fee': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': 'السعر',
                'min': '0', 'step': '0.01',
            }),
            'center_percentage': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': '30',
                'min': '0', 'max': '100', 'step': '0.01',
            }),
            'sessions_per_month': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': '8',
                'min': '1', 'max': str(MAX_SESSIONS_PER_CYCLE),
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A group being edited keeps its currently-assigned teacher in the
        # choices even if that teacher has since been deactivated or
        # soft-deleted — otherwise re-saving the group (it keeps generating
        # sessions regardless) fails with an "invalid choice" error the
        # moment its owner disappears from the active list, and the only way
        # out through this form is to blank the field.
        self.fields['teacher'].queryset = Teacher.all_objects.filter(
            Q(is_active=True, deleted_at__isnull=True) | Q(pk=self.instance.teacher_id)
        )
        self.fields['education_stage'].required = False
        self.fields['education_year'].required = False

    def clean_standard_fee(self):
        """السعر القياسي لا يمكن أن يكون بالسالب"""
        fee = self.cleaned_data.get('standard_fee')
        if fee is not None and fee < 0:
            raise forms.ValidationError('السعر القياسي لا يمكن أن يكون رقماً سالباً')
        return fee

    def clean_center_percentage(self):
        """نسبة السنتر يجب أن تكون بين 0 و 100"""
        percentage = self.cleaned_data.get('center_percentage')
        if percentage is not None and not (Decimal('0') <= percentage <= Decimal('100')):
            raise forms.ValidationError('نسبة السنتر يجب أن تكون بين 0 و 100')
        return percentage

    def clean_duration_minutes(self):
        """مدة الحصة يجب أن تكون أكبر من صفر"""
        duration = self.cleaned_data.get('duration_minutes')
        if duration is not None and duration < 1:
            raise forms.ValidationError('مدة الحصة يجب أن تكون دقيقة واحدة على الأقل')
        return duration

    def clean_sessions_per_month(self):
        """
        طول الدورة المحاسبية: من حصة واحدة إلى ``MAX_SESSIONS_PER_CYCLE``.

        الحد الأعلى مفروض على مستوى الموديل أيضًا؛ يُكرَّر هنا لتظهر الرسالة
        بالعربية داخل النموذج بدل خطأ التحقق العام.
        """
        sessions = self.cleaned_data.get('sessions_per_month')
        if sessions is not None and sessions < 1:
            raise forms.ValidationError('عدد الحصص في الشهر يجب أن يكون 1 على الأقل')
        if sessions is not None and sessions > MAX_SESSIONS_PER_CYCLE:
            raise forms.ValidationError(
                f'الدورة المحاسبية {MAX_SESSIONS_PER_CYCLE} حصص كحد أقصى'
            )
        return sessions

    @transaction.atomic
    def save_with_schedules(self, schedule_data, commit=True):
        """
        Save the group and rebuild its ``GroupSchedule`` rows.

        ``schedule_data``: ``[{'day': 'Saturday', 'time': time_obj, 'duration': 120,
        'room': Room_instance_or_None}, ...]``

        Two things this method has to get right:

        * **Atomicity** — the old schedules are deleted before the new ones are
          written. Without a transaction a failure part-way through (an overlap,
          a duplicated day) left the group with *no* schedule at all.
        * **Validation** — ``objects.create()`` never calls ``full_clean()``, so
          ``GroupSchedule.clean``'s room-overlap check was dead code and
          double-booked rooms were accepted silently.
        """
        group = super().save(commit=False)

        # Legacy columns still feed consumers outside this app; keep them
        # pointing at the first session. GroupSchedule remains the source of truth.
        group.sync_legacy_schedule_fields(schedule_data)

        if not commit:
            return group

        group.save()

        # Clear old schedules and create new ones
        GroupSchedule.objects.filter(group=group).delete()
        for entry in schedule_data:
            schedule = GroupSchedule(
                group=group,
                day_of_week=entry['day'],
                start_time=entry['time'],
                duration=entry.get('duration') or group.duration_minutes,
                room=entry.get('room'),
            )
            schedule.full_clean()
            schedule.save()

        return group


class SubjectForm(forms.ModelForm):
    """
    Form للمواد الدراسية
    موديل المواد الدراسية - إضافة، تعديل وحذف
    """
    class Meta:
        model = Subject
        fields = ['name', 'education_stage']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اسم المادة الدراسية',
                'autofocus': 'autofocus'
            }),
            'education_stage': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean(self):
        """
        Validate that the ``(name, education_stage)`` combination is unique.

        The check runs against ``all_objects``: the pair is unique at the
        database level, so a *soft-deleted* subject still occupies the name and
        recreating it would fail with a raw ``IntegrityError`` instead of a
        readable form error.
        """
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        education_stage = cleaned_data.get('education_stage', '')
        if name:
            queryset = Subject.all_objects.filter(name=name, education_stage=education_stage)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            existing = queryset.first()
            if existing is not None:
                if existing.deleted_at is not None:
                    raise forms.ValidationError(
                        'هذه المادة موجودة في سلة المهملات لنفس المرحلة الدراسية — يمكن استعادتها بدلاً من إضافتها من جديد'
                    )
                raise forms.ValidationError('هذه المادة موجودة بالفعل لنفس المرحلة الدراسية')
        return cleaned_data