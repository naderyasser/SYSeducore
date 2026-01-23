from django import forms
from .models import Student


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            'barcode', 'full_name', 'group', 'parent_phone',
            'financial_status', 'custom_fee', 'is_active'
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'barcode': forms.TextInput(attrs={'class': 'form-control'}),
            'parent_phone': forms.TextInput(attrs={'class': 'form-control'}),
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
