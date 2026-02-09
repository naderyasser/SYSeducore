from django import forms
from .models import Student, StudentGroupEnrollment


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
            'date_of_birth', 'school_name', 'grade', 'address', 'is_active'
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
            'school_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اسم المدرسة'
            }),
            'grade': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: الصف الثالث الثانوي'
            }),
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
        self.fields['grade'].required = False
        self.fields['address'].required = False
        self.fields['parent_name'].required = False
        # Both phones are required
        self.fields['student_phone'].required = True
        self.fields['parent_phone'].required = True
        # Education fields
        self.fields['education_stage'].required = False
        self.fields['education_year'].required = False

    def clean_student_code(self):
        code = self.cleaned_data.get('student_code')
        if code:
            code = code.strip()
            # Check if code already exists (exclude current instance if updating)
            qs = Student.objects.filter(student_code=code)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('هذا الكود مستخدم بالفعل لطالب آخر')
        return code

    def _clean_phone(self, phone):
        """Helper to normalize phone numbers - removes +20 prefix for storage"""
        if not phone:
            return phone
        phone = phone.replace(' ', '').replace('-', '').strip()
        # Remove +20 prefix if exists
        if phone.startswith('+20'):
            phone = '0' + phone[3:]
        elif phone.startswith('20') and len(phone) == 12:
            phone = '0' + phone[2:]
        # Ensure starts with 0
        if not phone.startswith('0') and len(phone) == 10:
            phone = '0' + phone
        return phone

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
        phone = self.cleaned_data.get('parent_phone', '')
        phone = phone.replace(' ', '').replace('-', '')
        if not phone.startswith('+'):
            if phone.startswith('0'):
                phone = '+20' + phone[1:]
            else:
                phone = '+20' + phone
        return phone


class StudentGroupEnrollmentForm(forms.ModelForm):
    """
    Form لتسجيل الطالب في المجموعة
    مع التحقق من توافق الجنس والمرحلة الدراسية
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

        # التحقق من توافق الجنس
        if student and group:
            if group.gender_type == 'male' and student.gender == 'female':
                raise forms.ValidationError(
                    'لا يمكن تسجيل طالبة في مجموعة مخصصة للبنين فقط'
                )
            if group.gender_type == 'female' and student.gender == 'male':
                raise forms.ValidationError(
                    'لا يمكن تسجيل طالب في مجموعة مخصصة للبنات فقط'
                )

            # التحقق من توافق المرحلة الدراسية
            if group.education_stage and student.education_stage:
                if group.education_stage != student.education_stage:
                    raise forms.ValidationError(
                        f'المجموعة مخصصة لمرحلة "{group.get_education_stage_display()}" '
                        f'والطالب في مرحلة "{student.get_education_stage_display()}"'
                    )
            if group.education_year and student.education_year:
                if group.education_year != student.education_year:
                    raise forms.ValidationError(
                        f'المجموعة مخصصة للسنة "{group.get_education_year_display()}" '
                        f'والطالب في السنة "{student.get_education_year_display()}"'
                    )

        return cleaned_data


class StudentFilterForm(forms.Form):
    """
    Form for filtering students
    """
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'بحث بالاسم، الكود، أو الهاتف...'
        })
    )
    group = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label='جميع المجموعات',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    status = forms.ChoiceField(
        choices=[
            ('', 'جميع الحالات'),
            ('with_groups', 'في مجموعة'),
            ('no_groups', 'بدون مجموعة'),
            ('active', 'نشط فقط'),
            ('inactive', 'غير نشط'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    grade = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'الصف الدراسي'
        })
    )

    def __init__(self, *args, **kwargs):
        from apps.teachers.models import Group
        super().__init__(*args, **kwargs)
        self.fields['group'].queryset = Group.objects.filter(is_active=True)
