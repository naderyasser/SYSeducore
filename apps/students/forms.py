from django import forms
from .models import Student, StudentGroupEnrollment


class StudentForm(forms.ModelForm):
    """
    Form للطالب (النظام الجديد: student_code بدل barcode)
    """
    class Meta:
        model = Student
        fields = ['student_code', 'full_name', 'parent_phone', 'is_active']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'student_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 1001'
            }),
            'parent_phone': forms.TextInput(attrs={'class': 'form-control'}),
        }


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
