from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import (
    authenticate,
    login,
    logout,
    get_user_model,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib import messages
from django.views.decorators.cache import never_cache
from django.http import HttpResponse, JsonResponse
from django.template import TemplateDoesNotExist, engines
from django.utils.http import url_has_allowed_host_and_scheme
from django_ratelimit.decorators import ratelimit

from .forms import LoginForm, UserCreateForm, UserUpdateForm
from .decorators import admin_required, ratelimit_key
from apps.attendance.models import ActivityLog

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wants_json(request):
    """True when the caller expects a JSON body rather than an HTML page."""
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return True
    content_type = (request.content_type or '')
    if content_type.startswith('application/json'):
        return True
    accept = request.headers.get('accept', '')
    if 'application/json' in accept and 'text/html' not in accept:
        return True
    return request.path.startswith('/api/')


def _render_with_fallback(request, template_name, context, fallback_template):
    """
    Render ``template_name`` if it exists, otherwise render the inline
    fallback. The templates/ directory is owned by another agent, so these
    views must not depend on files that are not there yet.
    """
    try:
        return render(request, template_name, context)
    except TemplateDoesNotExist:
        template = engines['django'].from_string(fallback_template)
        return HttpResponse(template.render(context, request))


def _style_form(form, css_class='form-control'):
    """Apply the project's Bootstrap input class to a plain Django form."""
    for field in form.fields.values():
        existing = field.widget.attrs.get('class', '')
        if css_class not in existing.split():
            field.widget.attrs['class'] = (existing + ' ' + css_class).strip()


USER_CREATED_FALLBACK_TEMPLATE = """{% extends 'base.html' %}
{% block title %}تم إنشاء المستخدم{% endblock %}
{% block page_title %}تم إنشاء المستخدم{% endblock %}
{% block content %}
<div class="card" style="padding:24px;max-width:640px;margin:0 auto;text-align:center;">
    <h2>تم إنشاء المستخدم "{{ created_user.username }}" بنجاح</h2>
    {% if generated_password %}
    <p>كلمة المرور المؤقتة — تظهر مرة واحدة فقط، يرجى تسليمها للمستخدم الآن:</p>
    <p style="font-family:monospace;font-size:1.5rem;direction:ltr;">{{ generated_password }}</p>
    <p>لن تظهر كلمة المرور مرة أخرى بعد مغادرة هذه الصفحة.</p>
    {% endif %}
    <p><a href="{% url 'accounts:user_list' %}" class="btn btn-primary">العودة إلى قائمة المستخدمين</a></p>
</div>
{% endblock %}
"""


PASSWORD_CHANGE_FALLBACK_TEMPLATE = """{% extends 'base.html' %}
{% block title %}تغيير كلمة المرور{% endblock %}
{% block page_title %}تغيير كلمة المرور{% endblock %}
{% block content %}
<div class="card" style="padding:24px;max-width:520px;margin:0 auto;">
    <form method="post" novalidate>
        {% csrf_token %}
        {% if form.errors %}
        <div class="alert alert-danger">
            {% for field, errors in form.errors.items %}
                {% for error in errors %}<div>{{ error }}</div>{% endfor %}
            {% endfor %}
        </div>
        {% endif %}
        {% for field in form %}
        <div class="mb-3">
            <label class="form-label" for="{{ field.id_for_label }}">{{ field.label }}</label>
            {{ field }}
        </div>
        {% endfor %}
        <button type="submit" class="btn btn-primary">حفظ كلمة المرور الجديدة</button>
        <a href="{% url 'reports:dashboard' %}" class="btn btn-secondary">إلغاء</a>
    </form>
</div>
{% endblock %}
"""


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------

def csrf_failure(request, reason=''):
    """
    Custom CSRF failure handler.

    AJAX / JSON callers get a JSON 403 so ``response.json()`` keeps working;
    a normal HTML form post keeps the friendly "session expired" redirect.
    """
    if _wants_json(request):
        return JsonResponse(
            {
                'success': False,
                'message': 'فشل التحقق من الحماية (CSRF)، يرجى تحديث الصفحة وإعادة المحاولة',
            },
            status=403,
        )
    messages.warning(request, 'انتهت صلاحية الجلسة، يرجى المحاولة مرة أخرى.')
    return redirect('accounts:login')


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------

@never_cache
@ratelimit(key=ratelimit_key, rate='5/m', method='POST', block=True)
def login_view(request):
    if request.user.is_authenticated:
        return redirect('reports:dashboard')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                messages.success(request, f'مرحباً {user.get_full_name()}')
                return redirect(_safe_next_url(request) or 'reports:dashboard')

            # ModelBackend returns None for inactive users too, so the
            # "account disabled" case has to be detected explicitly —
            # and only when the password was actually correct, so this
            # never becomes a username-enumeration oracle.
            if _is_inactive_account(username, password):
                messages.error(
                    request,
                    'حسابك غير نشط، يرجى التواصل مع إدارة المركز',
                )
            else:
                messages.error(request, 'اسم المستخدم أو كلمة المرور غير صحيحة')
    else:
        form = LoginForm()

    return render(request, 'auth/login.html', {'form': form})


def _is_inactive_account(username, password):
    """True only when the credentials are valid but the account is disabled."""
    candidate = User.objects.filter(username=username, is_active=False).first()
    return bool(candidate and candidate.check_password(password))


def _safe_next_url(request):
    """Return ?next= only when it points back at this host."""
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_secure=request.is_secure(),
    ):
        return next_url
    return None


@login_required
def logout_view(request):
    if request.method != 'POST':
        return redirect('reports:dashboard')
    logout(request)
    messages.success(request, 'تم تسجيل الخروج بنجاح')
    return redirect('accounts:login')


# ---------------------------------------------------------------------------
# Self-service password change
# ---------------------------------------------------------------------------

@never_cache
@login_required
def password_change(request):
    """Let the logged-in user change their own password."""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # Keep the user signed in after the hash changes.
            update_session_auth_hash(request, user)
            ActivityLog.log(
                user=request.user,
                action='user_update',
                description=f'تغيير كلمة المرور الشخصية: {user.username}',
                target_model='User',
                target_id=user.pk,
                request=request,
            )
            messages.success(request, 'تم تغيير كلمة المرور بنجاح')
            return redirect('reports:dashboard')
    else:
        form = PasswordChangeForm(request.user)

    _style_form(form)
    return _render_with_fallback(
        request,
        'accounts/password_change.html',
        {'form': form},
        PASSWORD_CHANGE_FALLBACK_TEMPLATE,
    )


# ---------------------------------------------------------------------------
# User management (admin only)
# ---------------------------------------------------------------------------

@admin_required
def user_list(request):
    users = User.objects.all().order_by('-created_at')
    return render(request, 'accounts/user_list.html', {'users': users})


@never_cache
@admin_required
def user_create(request):
    if request.method == 'POST':
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            generated_password = getattr(user, '_generated_password', None)

            ActivityLog.log(
                user=request.user,
                action='user_create',
                description=f'إنشاء مستخدم جديد: {user.username} ({user.get_role_display()})',
                target_model='User',
                target_id=user.pk,
                request=request,
            )

            if generated_password:
                # Shown once, on this response only: never put a plaintext
                # password in the messages framework, which persists it in
                # the DB-backed session until the next page load.
                return _render_with_fallback(
                    request,
                    'accounts/user_created.html',
                    {'created_user': user, 'generated_password': generated_password},
                    USER_CREATED_FALLBACK_TEMPLATE,
                )

            messages.success(request, f'تم إنشاء المستخدم "{user.username}" بنجاح')
            return redirect('accounts:user_list')
    else:
        form = UserCreateForm()
    return render(request, 'accounts/user_form.html', {'form': form, 'is_create': True})


@admin_required
def user_update(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        form = UserUpdateForm(
            request.POST, instance=target_user, request_user=request.user
        )
        if form.is_valid():
            updated_user = form.save()
            if updated_user.pk == request.user.pk and form.cleaned_data.get('new_password'):
                # Changing your own password rotates the session auth hash;
                # without this the admin is logged out on their next request.
                update_session_auth_hash(request, updated_user)
            ActivityLog.log(
                user=request.user,
                action='user_update',
                description=f'تعديل مستخدم: {target_user.username}',
                target_model='User',
                target_id=target_user.pk,
                request=request,
            )
            messages.success(request, f'تم تحديث المستخدم "{target_user.username}" بنجاح')
            return redirect('accounts:user_list')
    else:
        form = UserUpdateForm(instance=target_user, request_user=request.user)
    return render(request, 'accounts/user_form.html', {'form': form, 'is_create': False, 'target_user': target_user})


@admin_required
def user_toggle_status(request, user_id):
    if request.method != 'POST':
        messages.error(request, 'طريقة الطلب غير مسموح بها')
        return redirect('accounts:user_list')

    target_user = get_object_or_404(User, pk=user_id)
    if target_user == request.user:
        messages.error(request, 'لا يمكنك تعطيل حسابك الشخصي')
        return redirect('accounts:user_list')

    if target_user.is_active and _is_last_active_admin(target_user):
        messages.error(request, 'لا يمكن تعطيل آخر مدير نظام نشط في النظام')
        return redirect('accounts:user_list')

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=['is_active'])

    status = 'تفعيل' if target_user.is_active else 'تعطيل'
    ActivityLog.log(
        user=request.user,
        action='user_toggle',
        description=f'{status} مستخدم: {target_user.username}',
        target_model='User',
        target_id=target_user.pk,
        request=request,
    )

    messages.success(request, f'تم {status} المستخدم "{target_user.username}"')
    return redirect('accounts:user_list')


def _is_last_active_admin(user):
    """True when disabling/demoting ``user`` would leave zero active admins."""
    if user.role != 'admin' or not user.is_active:
        return False
    return not User.objects.filter(
        role='admin', is_active=True
    ).exclude(pk=user.pk).exists()
