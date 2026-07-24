from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
import secrets
import string

User = get_user_model()


class LoginForm(forms.Form):
    """
    Login form for users.
    """
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'اسم المستخدم'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'كلمة المرور'
        })
    )


def generate_password(length=12):
    """
    Generate a random password that satisfies AUTH_PASSWORD_VALIDATORS.

    The alphabet is alphanumeric (unambiguous when read aloud at the desk);
    the loop guards against the vanishingly rare all-numeric draw that the
    NumericPasswordValidator would reject.
    """
    chars = string.ascii_letters + string.digits
    for _ in range(20):
        candidate = ''.join(secrets.choice(chars) for _ in range(length))
        try:
            password_validation.validate_password(candidate)
        except ValidationError:
            continue
        return candidate
    # Extremely unlikely: fall back to a mixed-case + digit password.
    return 'Aa1' + ''.join(secrets.choice(chars) for _ in range(max(length - 3, 6)))


class _PasswordValidationMixin:
    """Runs Django's configured AUTH_PASSWORD_VALIDATORS on a form field."""

    def _password_owner(self, cleaned_data):
        """
        A User instance carrying the submitted identity fields, so the
        UserAttributeSimilarityValidator can compare the password against
        the username / name / email actually being saved.
        """
        user = getattr(self, 'instance', None) or User()
        return User(
            username=cleaned_data.get('username') or getattr(user, 'username', '') or '',
            first_name=cleaned_data.get('first_name') or getattr(user, 'first_name', '') or '',
            last_name=cleaned_data.get('last_name') or getattr(user, 'last_name', '') or '',
            email=cleaned_data.get('email') or getattr(user, 'email', '') or '',
        )

    def validate_password_field(self, field_name, password, cleaned_data):
        """Attach validator errors to ``field_name`` instead of raising a 500."""
        if not password:
            return
        try:
            password_validation.validate_password(
                password, self._password_owner(cleaned_data)
            )
        except ValidationError as exc:
            self.add_error(field_name, exc)


class UserCreateForm(_PasswordValidationMixin, forms.ModelForm):
    password1 = forms.CharField(
        label='كلمة المرور',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'كلمة المرور'}),
        required=False,
        help_text='اتركه فارغاً لتوليد كلمة مرور تلقائياً',
    )
    password2 = forms.CharField(
        label='تأكيد كلمة المرور',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'تأكيد كلمة المرور'}),
        required=False,
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'role', 'phone']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المستخدم'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الاسم الأول'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم العائلة'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'البريد الإلكتروني'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم الهاتف'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p1 != p2:
            self.add_error('password2', 'كلمتا المرور غير متطابقتين')
        elif p1:
            # Only validate a password the admin actually typed; generated
            # passwords are produced pre-validated in generate_password().
            self.validate_password_field('password1', p1, cleaned_data)
        return cleaned_data

    @staticmethod
    def generate_password(length=12):
        return generate_password(length)

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password1')
        generated = False
        if not password:
            password = self.generate_password()
            generated = True
        user.set_password(password)
        # Only exposed for the one-time confirmation render; never stored.
        user._generated_password = password if generated else None
        if commit:
            user.save()
        return user


class UserUpdateForm(_PasswordValidationMixin, forms.ModelForm):
    new_password = forms.CharField(
        label='كلمة مرور جديدة',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'اتركه فارغاً لعدم التغيير'}),
        required=False,
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'role', 'phone', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        # The admin performing the edit — used for the self-lockout guard.
        self.request_user = kwargs.pop('request_user', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()

        new_password = cleaned_data.get('new_password')
        if new_password:
            self.validate_password_field('new_password', new_password, cleaned_data)

        new_role = cleaned_data.get('role')
        # A missing/invalid is_active never means "deactivate" — fall back to
        # the stored value so a field error cannot silently disable the user.
        is_active = cleaned_data.get('is_active')
        if 'is_active' not in cleaned_data:
            is_active = self.instance.is_active

        self._check_self_lockout(new_role, is_active)
        self._check_last_admin(new_role, is_active)
        return cleaned_data

    def _is_editing_self(self):
        return bool(
            self.request_user
            and self.instance
            and self.instance.pk
            and self.request_user.pk == self.instance.pk
        )

    def _check_self_lockout(self, new_role, is_active):
        """An admin must not be able to demote or disable their own account."""
        if not self._is_editing_self():
            return
        if not is_active:
            self.add_error('is_active', 'لا يمكنك تعطيل حسابك الشخصي')
        if self.instance.role == 'admin' and new_role and new_role != 'admin':
            self.add_error('role', 'لا يمكنك تغيير دور حسابك الشخصي من مدير النظام')

    def _check_last_admin(self, new_role, is_active):
        """The system must always keep at least one active admin."""
        if not self.instance or not self.instance.pk:
            return
        if self.instance.role != 'admin' or not self.instance.is_active:
            return
        still_admin = (new_role or self.instance.role) == 'admin' and is_active
        if still_admin:
            return
        other_active_admins = User.objects.filter(
            role='admin', is_active=True
        ).exclude(pk=self.instance.pk).exists()
        if not other_active_admins:
            self.add_error(
                None,
                'لا يمكن تعطيل أو تغيير دور آخر مدير نظام نشط في النظام',
            )

    def save(self, commit=True):
        user = super().save(commit=False)
        new_password = self.cleaned_data.get('new_password')
        if new_password:
            user.set_password(new_password)
        if commit:
            user.save()
        return user
