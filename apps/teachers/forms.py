from django import forms
from .models import Teacher, Group, Room


class TeacherForm(forms.ModelForm):
    class Meta:
        model = Teacher
        fields = ['full_name', 'phone', 'email', 'specialization', 'hire_date', 'is_active']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المدرس'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '01xxxxxxxxx'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'example@email.com'}),
            'specialization': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'التخصص'}),
            'hire_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


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
    class Meta:
        model = Group
        fields = ['group_name', 'teacher', 'room', 'schedule_day', 'schedule_time', 'standard_fee', 'center_percentage', 'is_active']
        widgets = {
            'group_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المجموعة'}),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'room': forms.Select(attrs={'class': 'form-select'}),
            'schedule_day': forms.Select(attrs={'class': 'form-select'}),
            'schedule_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'standard_fee': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'السعر'}),
            'center_percentage': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '30'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['teacher'].queryset = Teacher.objects.filter(is_active=True)
        self.fields['room'].queryset = Room.objects.filter(is_active=True)
        self.fields['room'].required = False
