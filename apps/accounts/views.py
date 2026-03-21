from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.cache import never_cache
from django.http import JsonResponse

from .forms import LoginForm, UserCreateForm, UserUpdateForm
from .decorators import admin_required
from apps.attendance.models import ActivityLog

User = get_user_model()


def csrf_failure(request, reason=''):
    """Custom CSRF failure handler: redirects to login with a clear message."""
    messages.warning(request, 'انتهت صلاحية الجلسة، يرجى المحاولة مرة أخرى.')
    return redirect('accounts:login')


@never_cache
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
                if user.is_active:
                    login(request, user)
                    messages.success(request, f'مرحباً {user.get_full_name()}')
                    return redirect('reports:dashboard')
                else:
                    messages.error(request, 'حسابك غير نشط')
            else:
                messages.error(request, 'اسم المستخدم أو كلمة المرور غير صحيحة')
    else:
        form = LoginForm()

    return render(request, 'auth/login.html', {'form': form})


@login_required
def logout_view(request):
    if request.method != 'POST':
        return redirect('reports:dashboard')
    logout(request)
    messages.success(request, 'تم تسجيل الخروج بنجاح')
    return redirect('accounts:login')


@login_required
@admin_required
def user_list(request):
    users = User.objects.all().order_by('-created_at')
    return render(request, 'accounts/user_list.html', {'users': users})


@login_required
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
                messages.success(
                    request,
                    f'تم إنشاء المستخدم "{user.username}" بنجاح. كلمة المرور: {generated_password}'
                )
            else:
                messages.success(request, f'تم إنشاء المستخدم "{user.username}" بنجاح')
            return redirect('accounts:user_list')
    else:
        form = UserCreateForm()
    return render(request, 'accounts/user_form.html', {'form': form, 'is_create': True})


@login_required
@admin_required
def user_update(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        form = UserUpdateForm(request.POST, instance=target_user)
        if form.is_valid():
            form.save()
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
        form = UserUpdateForm(instance=target_user)
    return render(request, 'accounts/user_form.html', {'form': form, 'is_create': False, 'target_user': target_user})


@login_required
@admin_required
def user_toggle_status(request, user_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'})

    target_user = get_object_or_404(User, pk=user_id)
    if target_user == request.user:
        return JsonResponse({'success': False, 'message': 'لا يمكنك تعطيل حسابك الشخصي'})

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=['is_active'])

    status = 'تفعيل' if target_user.is_active else 'تعطيل'
    ActivityLog.log(
        user=request.user,
        action='user_update',
        description=f'{status} مستخدم: {target_user.username}',
        target_model='User',
        target_id=target_user.pk,
        request=request,
    )

    messages.success(request, f'تم {status} المستخدم "{target_user.username}"')
    return redirect('accounts:user_list')
