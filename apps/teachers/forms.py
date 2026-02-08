from django import forms
from .models import Teacher, Group, Room, Subject


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


class GroupForm(forms.ModelForm):
    """
    Form للمجموعة مع الحقول الجديدة:
    - مدة الحصة
    - تصنيف الجنس
    - المرحلة والسنة الدراسية
    - متعدد الأيام (يتم التعامل مع schedule_day بالكاستوم شيكبكس)
    """
    schedule_day = forms.ChoiceField(
        choices=[],
        required=False,
        widget=forms.HiddenInput()
    )

    class Meta:
        model = Group
        fields = [
            'group_name', 'teacher', 'room', 'schedule_day', 'schedule_time',
            'duration_minutes', 'gender_type', 'education_stage', 'education_year',
            'standard_fee', 'center_percentage', 'is_active'
        ]
        widgets = {
            'group_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المجموعة'}),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'room': forms.Select(attrs={'class': 'form-select'}),
            'schedule_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'duration_minutes': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '120',
                'min': '30',
                'step': '15',
            }),
            'gender_type': forms.Select(attrs={'class': 'form-select'}),
            'education_stage': forms.Select(attrs={'class': 'form-select'}),
            'education_year': forms.Select(attrs={'class': 'form-select'}),
            'standard_fee': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'السعر'}),
            'center_percentage': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '30'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['teacher'].queryset = Teacher.objects.filter(is_active=True)
        self.fields['room'].queryset = Room.objects.filter(is_active=True)
        self.fields['room'].required = False
        self.fields['education_stage'].required = False
        self.fields['education_year'].required = False

class SubjectForm(forms.ModelForm):
    """
    Form للمواد الدراسية
    موديل المواد الدراسية - إضافة، تعديل وحذف
    """
    class Meta:
        model = Subject
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اسم المادة الدراسية',
                'autofocus': 'autofocus'
            }),
        }

    def clean_name(self):
        """Validate that the name is unique"""
        name = self.cleaned_data.get('name')
        if name:
            # Check if another subject with this name exists (excluding current edit)
            queryset = Subject.objects.filter(name=name)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise forms.ValidationError('هذه المادة موجودة بالفعل')
        return name