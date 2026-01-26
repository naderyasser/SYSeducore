from django import forms
from .models import Student, StudentGroupEnrollment


class StudentForm(forms.ModelForm):
    """
    Form للطالب (النظام الجديد: student_code بدل barcode)
    - إذا ترك الكود فارغ، يتم توليده تلقائياً (آخر كود + 1)
    - يمكن للأدمن إدخال كود مخصص يدوياً
    """
    class Meta:
        model = Student
        fields = ['student_code', 'full_name', 'parent_phone', 'is_active']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'student_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'اتركه فارغ للتوليد التلقائي أو أدخل كود مخصص'
            }),
            'parent_phone': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student_code'].required = False

    def clean_student_code(self):
        code = self.cleaned_data.get('student_code')
        if not code or code.strip() == '':
            code = self.generate_next_code()
        return code.strip()

    def generate_next_code(self):
        """توليد الكود التالي (آخر كود رقمي + 1)، يبدأ من 1001"""
        from django.db.models import Max
        from django.db.models.functions import Cast
        from django.db.models import IntegerField

        last_numeric = Student.objects.filter(
            student_code__regex=r'^\d+$'
        ).annotate(
            code_int=Cast('student_code', IntegerField())
        ).aggregate(max_code=Max('code_int'))

        last_code = last_numeric.get('max_code')
        return str(last_code + 1) if last_code else '1001'


class StudentGroupEnrollmentForm(forms.ModelForm):
    """
    Form لتسجيل الطالب في المجموعة
    """
    class Meta:
        model = StudentGroupEnrollment
        fields = ['student', 'group', 'financial_status', 'custom_fee', 'is_active']
        widgets = {
            'financial_status': forms.Select(attrs={'class': 'form-control'}),
            'custom_fee': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        financial_status = cleaned_data.get('financial_status')
        custom_fee = cleaned_data.get('custom_fee')

        # إذا كانت الحالة رمزي، المبلغ المخصص مطلوب
        if financial_status == 'symbolic' and not custom_fee:
            raise forms.ValidationError(
                'يجب تحديد المبلغ المخصص للطلاب ذوي المبلغ الرمزي'
            )

        return cleaned_data
