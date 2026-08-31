from django import forms

from apps.core import education

from .models import Student, StudentGroupEnrollment
from .utils import enrollment_compatibility_errors, normalize_phone


class StudentForm(forms.ModelForm):
    """
    Form للطالب الشامل مع كل البيانات الإضافية
    - النوع (Gender)
    - المرحلة الدراسية + السنة + نوع التعليم
    - رقمين تواصل إجباريين (الطالب + ولي الأمر)
    """
    class Meta:
        model = Student
        fields = [
            'student_code', 'full_name', 'gender',
            'education_stage', 'education_year', 'education_type',
            'student_phone', 'parent_phone', 'parent_name',
            'date_of_birth', 'school_name', 'address', 'is_active'
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اسم الطالب الكامل'
            }),
            'student_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اتركه فارغ للتوليد التلقائي أو أدخل كود مخصص'
            }),
            'gender': forms.Select(attrs={
                'class': 'form-select',
            }),
            'education_stage': forms.Select(attrs={
                'class': 'form-select',
            }),
            'education_year': forms.Select(attrs={
                'class': 'form-select',
            }),
            'education_type': forms.Select(attrs={
                'class': 'form-select',
            }),
            'student_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'رقم هاتف الطالب: 01xxxxxxxxx'
            }),
            'parent_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'رقم ولي الأمر: 01xxxxxxxxx'
            }),
            'parent_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اسم ولي الأمر'
            }),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'school_name': forms.HiddenInput(),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'عنوان السكن',
                'rows': 2
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student_code'].required = False
        self.fields['date_of_birth'].required = False
        self.fields['school_name'].required = False
        self.fields['address'].required = False
        self.fields['parent_name'].required = False
        # Both phones are required
        self.fields['student_phone'].required = True
        self.fields['parent_phone'].required = True
        # Education fields
        self.fields['education_stage'].required = False
        self.fields['education_year'].required = False
        
        # Clean phone numbers on initial display (remove +20 prefix)
        if self.instance and self.instance.pk:
            if self.instance.student_phone:
                self.initial['student_phone'] = self._clean_phone(self.instance.student_phone)
            if self.instance.parent_phone:
                self.initial['parent_phone'] = self._clean_phone(self.instance.parent_phone)

    def clean(self):
        """
        Keep ``education_year`` consistent with ``education_stage``.

        The dropdown is rebuilt client-side per stage, but a stale value can
        still be posted — the user picks ابتدائي/السادس, switches to إعدادي,
        and a browser that ignored the rebuild (or a form replayed from the
        back button) sends "6" for a stage that only has three years. تأسيس
        and كورسات have no year at all. Both cases blank the year rather than
        rejecting the form: the field is optional, and a validation error over
        a dropdown the user can no longer see is a dead end.
        """
        cleaned = super().clean()
        cleaned['education_year'] = education.normalize_stage_year(
            cleaned.get('education_stage'), cleaned.get('education_year'),
        )
        return cleaned

    def clean_student_code(self):
        code = self.cleaned_data.get('student_code')
        if code:
            code = code.strip()
            # ``student_code`` is UNIQUE at the database level and Student is
            # soft-deletable, so validating against ``objects`` (alive rows
            # only) let a recycled code through and blew up with an
            # IntegrityError at save time. Validate against ``all_objects``.
            qs = Student.all_objects.filter(student_code=code)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            clash = qs.first()
            if clash is not None:
                if clash.deleted_at is not None:
                    raise forms.ValidationError(
                        'هذا الكود مستخدم بالفعل لطالب محذوف موجود في سلة المهملات. '
                        'يرجى اختيار كود آخر أو استعادة الطالب المحذوف.'
                    )
                raise forms.ValidationError('هذا الكود مستخدم بالفعل لطالب آخر')
        return code

    def _clean_phone(self, phone):
        """Normalize a phone number to the app-wide stored format ``01xxxxxxxxx``."""
        return normalize_phone(phone)

    def clean_parent_phone(self):
        phone = self.cleaned_data.get('parent_phone', '')
        return self._clean_phone(phone)

    def clean_student_phone(self):
        phone = self.cleaned_data.get('student_phone', '')
        if phone:
            return self._clean_phone(phone)
        return phone


class StudentQuickForm(forms.ModelForm):
    """
    Form سريع لإضافة طالب بحد أدنى من البيانات
    """
    class Meta:
        model = Student
        fields = ['full_name', 'parent_phone']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اسم الطالب الكامل'
            }),
            'parent_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '01xxxxxxxxx'
            }),
        }

    def clean_parent_phone(self):
        # Same canonical format as StudentForm ('01xxxxxxxxx'). This form used
        # to store '+201xxxxxxxxx', so the very same number looked like two
        # different contacts depending on which dialog created the student.
        return normalize_phone(self.cleaned_data.get('parent_phone', ''))


class StudentGroupEnrollmentForm(forms.ModelForm):
    """
    Form لتسجيل الطالب في المجموعة
    مع التحقق من توافق الجنس والمرحلة الدراسية

    The compatibility rules live in ``students.utils.enrollment_compatibility_errors``
    and are shared with the ``add_to_group`` API so both paths reject the same
    enrollments.
    """
    class Meta:
        model = StudentGroupEnrollment
        fields = ['student', 'group', 'financial_status', 'custom_fee', 'is_active']
        widgets = {
            'financial_status': forms.Select(attrs={'class': 'form-select'}),
            'custom_fee': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'المبلغ المخصص (للحالة الرمزية)'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['custom_fee'].required = False

    def clean(self):
        cleaned_data = super().clean()
        financial_status = cleaned_data.get('financial_status')
        custom_fee = cleaned_data.get('custom_fee')
        student = cleaned_data.get('student')
        group = cleaned_data.get('group')

        # إذا كانت الحالة رمزي، المبلغ المخصص مطلوب
        if financial_status == 'symbolic' and not custom_fee:
            raise forms.ValidationError(
                'يجب تحديد المبلغ المخصص للطلاب ذوي المبلغ الرمزي'
            )

        # التحقق من توافق الجنس والمرحلة الدراسية
        errors = enrollment_compatibility_errors(student, group)
        if errors:
            raise forms.ValidationError(errors)

        return cleaned_data
