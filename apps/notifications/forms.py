from django import forms
from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.models import Group
from .models import WhatsAppTemplate


class SendWhatsAppMessageForm(forms.Form):
    """
    نموذج لإرسال رسالة واتساب لطالب واحد أو مجموعة
    """
    RECIPIENT_TYPE_CHOICES = [
        ('student', 'رسالة للطالب'),
        ('parent', 'رسالة لولي الأمر'),
        ('group', 'رسالة لمجموعة'),
    ]

    recipient_type = forms.ChoiceField(
        choices=RECIPIENT_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='نوع المستقبل'
    )

    student = forms.ModelChoiceField(
        queryset=Student.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='الطالب',
        required=False,
        empty_label='-- اختر طالب --'
    )

    group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='المجموعة',
        required=False,
        empty_label='-- اختر مجموعة --'
    )

    phone_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+966501234567 أو 0501234567',
            'pattern': r'^\+?[0-9\s\-\(\)]+$'
        }),
        label='رقم الهاتف',
        required=False,
        help_text='اختياري: إذا أردت إرسال لرقم مباشر'
    )

    message_template = forms.ModelChoiceField(
        queryset=WhatsAppTemplate.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='قالب الرسالة',
        required=False,
        empty_label='-- لا تستخدم قالب --'
    )

    message_text = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': 'اكتب نص الرسالة هنا...',
            'maxlength': '4096'
        }),
        label='نص الرسالة',
        help_text='الحد الأقصى: 4096 حرف'
    )

    include_student_name = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='إضافة اسم الطالب في الرسالة'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # تخصيص الـ CSS للحقول
        for field_name, field in self.fields.items():
            if field_name not in ['include_student_name']:
                # Don't overwrite form-select with form-control
                current_class = field.widget.attrs.get('class', '')
                if 'form-select' not in current_class:
                    field.widget.attrs.update({'class': 'form-control'})

    def clean(self):
        cleaned_data = super().clean()
        recipient_type = cleaned_data.get('recipient_type')
        student = cleaned_data.get('student')
        group = cleaned_data.get('group')
        phone_number = cleaned_data.get('phone_number')
        message_text = cleaned_data.get('message_text')

        # التحقق من أن الرسالة غير فارغة
        if not message_text or not message_text.strip():
            raise forms.ValidationError('نص الرسالة مطلوب')

        # التحقق من المستقبل بناءً على النوع
        if recipient_type == 'student':
            if not student and not phone_number:
                raise forms.ValidationError('اختر طالب أو أدخل رقم هاتف')
            if student and not student.student_phone:
                raise forms.ValidationError(f'الطالب {student.full_name} لا يملك رقم هاتف')

        elif recipient_type == 'parent':
            if not student and not phone_number:
                raise forms.ValidationError('اختر طالب أو أدخل رقم هاتف')
            if student and not student.parent_phone:
                raise forms.ValidationError(f'الطالب {student.full_name} لا يملك رقم ولي أمر')

        elif recipient_type == 'group':
            if not group:
                raise forms.ValidationError('اختر مجموعة')

        return cleaned_data


class BulkWhatsAppForm(forms.Form):
    """
    نموذج لإرسال رسائل جماعية
    """
    BULK_TYPE_CHOICES = [
        ('group', 'لجميع طلاب مجموعة'),
        ('custom_list', 'قائمة أرقام مخصصة'),
        ('attendance_report', 'تقرير حضور'),
    ]

    bulk_type = forms.ChoiceField(
        choices=BULK_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='نوع الإرسال الجماعي'
    )

    group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='المجموعة',
        required=False,
        empty_label='-- اختر مجموعة --'
    )

    recipient_role = forms.ChoiceField(
        choices=[
            ('parent', 'أولياء الأمور'),
            ('student', 'الطلاب'),
            ('both', 'الطلاب وأولياء الأمور'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='المستقبلون',
        required=False,
        initial='parent'
    )

    phone_numbers = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': '+966501234567\n+966502345678\n0501234567',
            'dir': 'ltr'
        }),
        label='قائمة الأرقام',
        required=False,
        help_text='أرقام هواتف مفصولة بأسطر جديدة (مع أو بدون +966)'
    )

    message_template = forms.ModelChoiceField(
        queryset=WhatsAppTemplate.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='قالب الرسالة',
        required=False,
        empty_label='-- اكتب رسالة مخصصة --'
    )

    message_text = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': 'اكتب نص الرسالة...'
        }),
        label='نص الرسالة',
        required=False
    )

    def clean(self):
        cleaned_data = super().clean()
        bulk_type = cleaned_data.get('bulk_type')
        group = cleaned_data.get('group')
        phone_numbers = cleaned_data.get('phone_numbers')
        message_text = cleaned_data.get('message_text')

        if bulk_type == 'group' and not group:
            raise forms.ValidationError('اختر مجموعة')

        if bulk_type == 'custom_list' and not phone_numbers:
            raise forms.ValidationError('أدخل قائمة الأرقام')

        if not message_text or not message_text.strip():
            raise forms.ValidationError('نص الرسالة مطلوب')

        return cleaned_data
