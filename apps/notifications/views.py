from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.contrib import messages as django_messages
from django.conf import settings
from django.db.models import Q, Count
import json
from .services import WhatsAppService
from .models import WhatsAppMessage, WhatsAppTemplate
from .forms import SendWhatsAppMessageForm, BulkWhatsAppForm
from apps.teachers.models import Group
from apps.students.models import Student, StudentGroupEnrollment


def whatsapp_required(view_func):
    """Block access to WhatsApp views when notifications are disabled."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if getattr(settings, 'NOTIFICATION_METHOD', 'none') != 'whatsapp':
            django_messages.warning(request, 'خدمة الواتساب معطلة حالياً')
            return redirect('reports:dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


@login_required
@whatsapp_required
def whatsapp_dashboard(request):
    """
    لوحة تحكم إدارة الواتساب
    """
    # إحصائيات الرسائل
    today_messages = WhatsAppMessage.objects.filter(
        created_at__date=timezone.now().date()
    )
    
    stats = {
        'total_today': today_messages.count(),
        'sent_today': today_messages.filter(status='sent').count(),
        'pending_today': today_messages.filter(status='pending').count(),
        'failed_today': today_messages.filter(status='failed').count(),
        'total_all_time': WhatsAppMessage.objects.count(),
    }

    # آخر الرسائل
    recent_messages = WhatsAppMessage.objects.all()[:20]

    # المجموعات المتاحة
    groups = Group.objects.all()

    context = {
        'stats': stats,
        'recent_messages': recent_messages,
        'groups': groups,
        'page_title': 'إدارة الواتساب'
    }

    return render(request, 'notifications/whatsapp_dashboard.html', context)


@login_required
@whatsapp_required
def send_message(request):
    """
    صفحة إرسال رسالة واتساب فردية
    """
    if request.method == 'POST':
        form = SendWhatsAppMessageForm(request.POST)
        if form.is_valid():
            try:
                recipient_type = form.cleaned_data['recipient_type']
                student = form.cleaned_data.get('student')
                group = form.cleaned_data.get('group')
                phone_number = form.cleaned_data.get('phone_number')
                message_text = form.cleaned_data['message_text']
                template = form.cleaned_data.get('message_template')
                include_name = form.cleaned_data.get('include_student_name', False)

                # استخدام القالب إذا تم اختياره
                if template:
                    message_text = template.message_text

                whatsapp_service = WhatsAppService()
                
                if recipient_type == 'student':
                    if student:
                        phone = student.student_phone
                        final_message = message_text
                        if include_name:
                            final_message = f"مرحباً {student.full_name}\n\n{message_text}"
                    else:
                        phone = phone_number
                        final_message = message_text

                    # إرسال الرسالة
                    result = whatsapp_service.send_message(phone, final_message)

                    # حفظ سجل الرسالة
                    msg_record = WhatsAppMessage.objects.create(
                        phone_number=phone,
                        message_text=final_message,
                        message_type='student',
                        student=student,
                        sent_by=request.user,
                        status='sent' if result.get('success') else 'failed',
                        sent_at=timezone.now() if result.get('success') else None,
                        error_message=result.get('error', '')
                    )

                    if result.get('success'):
                        django_messages.success(request, f'تم إرسال الرسالة بنجاح إلى {phone}')
                    else:
                        django_messages.error(request, f'فشل الإرسال: {result.get("error", "خطأ غير معروف")}')

                elif recipient_type == 'parent':
                    if student:
                        phone = student.parent_phone
                        final_message = message_text
                        if include_name:
                            final_message = f"أولياء أمور الطالب {student.full_name}\n\n{message_text}"
                    else:
                        phone = phone_number
                        final_message = message_text

                    result = whatsapp_service.send_message(phone, final_message)

                    msg_record = WhatsAppMessage.objects.create(
                        phone_number=phone,
                        message_text=final_message,
                        message_type='parent',
                        student=student,
                        sent_by=request.user,
                        status='sent' if result.get('success') else 'failed',
                        sent_at=timezone.now() if result.get('success') else None,
                        error_message=result.get('error', '')
                    )

                    if result.get('success'):
                        django_messages.success(request, f'تم إرسال الرسالة بنجاح إلى {phone}')
                    else:
                        django_messages.error(request, f'فشل الإرسال: {result.get("error", "خطأ غير معروف")}')

                elif recipient_type == 'group':
                    # إرسال لجميع طلاب المجموعة
                    enrollments = StudentGroupEnrollment.objects.filter(
                        group=group,
                        is_active=True
                    ).select_related('student')

                    success_count = 0
                    fail_count = 0

                    for enrollment in enrollments:
                        student_obj = enrollment.student
                        phone = student_obj.parent_phone  # نرسل لأولياء الأمور افتراضياً
                        final_message = message_text
                        if include_name:
                            final_message = f"أولياء أمور الطالب {student_obj.full_name}\n\n{message_text}"

                        result = whatsapp_service.send_message(phone, final_message)

                        if result.get('success'):
                            success_count += 1
                        else:
                            fail_count += 1

                        # حفظ السجل
                        WhatsAppMessage.objects.create(
                            phone_number=phone,
                            message_text=final_message,
                            message_type='group',
                            student=student_obj,
                            group=group,
                            sent_by=request.user,
                            status='sent' if result.get('success') else 'failed',
                            sent_at=timezone.now() if result.get('success') else None,
                            error_message=result.get('error', '')
                        )

                    django_messages.success(request, f'تم الإرسال: {success_count} نجح, {fail_count} فشل')

                return redirect('notifications:whatsapp_dashboard')

            except Exception as e:
                django_messages.error(request, f'حدث خطأ: {str(e)}')

    else:
        form = SendWhatsAppMessageForm()

    context = {
        'form': form,
        'page_title': 'إرسال رسالة واتساب'
    }
    return render(request, 'notifications/send_message.html', context)


@login_required
@whatsapp_required
def send_bulk_message(request):
    """
    صفحة الإرسال الجماعي
    """
    if request.method == 'POST':
        form = BulkWhatsAppForm(request.POST)
        if form.is_valid():
            try:
                bulk_type = form.cleaned_data['bulk_type']
                message_text = form.cleaned_data['message_text']
                template = form.cleaned_data.get('message_template')

                if template:
                    message_text = template.message_text

                whatsapp_service = WhatsAppService()
                phone_list = []

                if bulk_type == 'group':
                    group = form.cleaned_data['group']
                    recipient_role = form.cleaned_data.get('recipient_role', 'parent')

                    enrollments = StudentGroupEnrollment.objects.filter(
                        group=group,
                        is_active=True
                    ).select_related('student')

                    for enrollment in enrollments:
                        if recipient_role == 'parent':
                            if enrollment.student.parent_phone:
                                phone_list.append({
                                    'phone': enrollment.student.parent_phone,
                                    'student': enrollment.student
                                })
                        elif recipient_role == 'student':
                            if enrollment.student.student_phone:
                                phone_list.append({
                                    'phone': enrollment.student.student_phone,
                                    'student': enrollment.student
                                })
                        else:  # both
                            if enrollment.student.parent_phone:
                                phone_list.append({
                                    'phone': enrollment.student.parent_phone,
                                    'student': enrollment.student,
                                    'role': 'parent'
                                })
                            if enrollment.student.student_phone:
                                phone_list.append({
                                    'phone': enrollment.student.student_phone,
                                    'student': enrollment.student,
                                    'role': 'student'
                                })

                elif bulk_type == 'custom_list':
                    phone_numbers = form.cleaned_data['phone_numbers']
                    for phone in phone_numbers.split('\n'):
                        phone = phone.strip()
                        if phone:
                            phone_list.append({'phone': phone})

                # إرسال الرسائل
                success_count = 0
                fail_count = 0

                for item in phone_list:
                    phone = item['phone']
                    student = item.get('student')
                    result = whatsapp_service.send_message(phone, message_text)

                    if result.get('success'):
                        success_count += 1
                        status = 'sent'
                    else:
                        fail_count += 1
                        status = 'failed'

                    # حفظ السجل
                    WhatsAppMessage.objects.create(
                        phone_number=phone,
                        message_text=message_text,
                        message_type=bulk_type,
                        student=student,
                        sent_by=request.user,
                        status=status,
                        sent_at=timezone.now() if status == 'sent' else None,
                        error_message=result.get('error', '')
                    )

                django_messages.success(request, f'تم الإرسال الجماعي: {success_count} نجح, {fail_count} فشل')
                return redirect('notifications:whatsapp_dashboard')

            except Exception as e:
                django_messages.error(request, f'حدث خطأ: {str(e)}')

    else:
        form = BulkWhatsAppForm()

    context = {
        'form': form,
        'page_title': 'الإرسال الجماعي'
    }
    return render(request, 'notifications/send_bulk_message.html', context)


@login_required
@whatsapp_required
def message_history(request):
    """
    سجل الرسائل المرسلة
    """
    messages_query = WhatsAppMessage.objects.all()

    # التصفية بناءً على الحالة
    status = request.GET.get('status')
    if status:
        messages_query = messages_query.filter(status=status)

    # التصفية بناءً على النوع
    msg_type = request.GET.get('type')
    if msg_type:
        messages_query = messages_query.filter(message_type=msg_type)

    # البحث
    search = request.GET.get('search')
    if search:
        messages_query = messages_query.filter(
            Q(phone_number__icontains=search) |
            Q(message_text__icontains=search)
        )

    # الترتيب
    messages_query = messages_query.order_by('-created_at')

    # العد
    message_count = messages_query.count()
    stats = {
        'total': message_count,
        'sent': messages_query.filter(status='sent').count(),
        'failed': messages_query.filter(status='failed').count(),
        'pending': messages_query.filter(status='pending').count(),
    }

    context = {
        'messages': messages_query[:100],  # آخر 100 رسالة
        'stats': stats,
        'status_filter': status,
        'type_filter': msg_type,
        'search_query': search,
        'page_title': 'سجل الرسائل'
    }

    return render(request, 'notifications/message_history.html', context)


@login_required
@whatsapp_required
def contact_list(request):
    """
    قائمة جهات الاتصال (الطلاب وأولياء الأمور)
    """
    contact_type = request.GET.get('type', 'all')  # all, student, parent

    if contact_type == 'student':
        contacts = Student.objects.filter(is_active=True, student_phone__isnull=False)
    elif contact_type == 'parent':
        contacts = Student.objects.filter(is_active=True, parent_phone__isnull=False)
    else:
        contacts = Student.objects.filter(is_active=True)

    # البحث
    search = request.GET.get('search')
    if search:
        contacts = contacts.filter(
            Q(full_name__icontains=search) |
            Q(student_code__icontains=search) |
            Q(student_phone__icontains=search) |
            Q(parent_phone__icontains=search)
        )

    contacts = contacts.order_by('full_name')

    context = {
        'contacts': contacts,
        'contact_type': contact_type,
        'search_query': search,
        'page_title': 'قائمة جهات الاتصال'
    }

    return render(request, 'notifications/contact_list.html', context)


@login_required
@whatsapp_required
def manage_templates(request):
    """
    إدارة قوالب الرسائل
    """
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            name = request.POST.get('name')
            description = request.POST.get('description')
            message_text = request.POST.get('message_text')

            if name and message_text:
                WhatsAppTemplate.objects.create(
                    name=name,
                    description=description,
                    message_text=message_text
                )
                django_messages.success(request, f'تم إنشاء القالب "{name}" بنجاح')
            else:
                django_messages.error(request, 'الاسم والنص مطلوبان')

        elif action == 'delete':
            template_id = request.POST.get('template_id')
            try:
                template = WhatsAppTemplate.objects.get(pk=template_id)
                template.delete()
                django_messages.success(request, 'تم حذف القالب بنجاح')
            except WhatsAppTemplate.DoesNotExist:
                django_messages.error(request, 'القالب غير موجود')

        return redirect('notifications:manage_templates')

    templates = WhatsAppTemplate.objects.all()

    context = {
        'templates': templates,
        'page_title': 'إدارة قوالب الرسائل'
    }

    return render(request, 'notifications/manage_templates.html', context)


@login_required
@whatsapp_required
def test_whatsapp(request):
    """
    Test WhatsApp sending (for development only).
    """
    if request.method == 'POST':
        phone = request.POST.get('phone')
        message = request.POST.get('message')

        whatsapp_service = WhatsAppService()
        result = whatsapp_service.send_message(phone, message)

        return JsonResponse(result)

    return render(request, 'notifications/test.html')


@login_required
@require_http_methods(["POST"])
def send_bulk_attendance_report(request):
    """
    API: إرسال تقرير حضور/غياب جماعي عبر الواتساب
    الإرسال الجماعي إلى أولياء أمور مجموعة كاملة
    """
    try:
        data = json.loads(request.body)
        group_id = data.get('group_id')
        session_date = data.get('session_date')  # Optional YYYY-MM-DD

        if not group_id:
            return JsonResponse({
                'success': False,
                'error': 'معرف المجموعة مطلوب'
            }, status=400)

        group = Group.objects.get(pk=group_id)

        whatsapp_service = WhatsAppService()

        from datetime import datetime as dt
        date = dt.strptime(session_date, '%Y-%m-%d').date() if session_date else None

        result = whatsapp_service.send_bulk_attendance_report(group, date)

        return JsonResponse({
            'success': True,
            'message': f'تم إرسال التقرير: {result.get("success_count", 0)} ناجح / {result.get("fail_count", 0)} فاشل',
            'details': result
        })

    except Group.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'المجموعة غير موجودة'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def send_bulk_custom_message(request):
    """
    API: إرسال رسالة مخصصة جماعية
    يمكن إرسال تنبيهات إلى قائمة أرقام
    """
    try:
        data = json.loads(request.body)
        phone_numbers = data.get('phone_numbers', [])
        message = data.get('message', '')
        group_id = data.get('group_id')  # Optional: send to all parents in group

        if not message:
            return JsonResponse({
                'success': False,
                'error': 'نص الرسالة مطلوب'
            }, status=400)

        # If group_id provided, get all parent phones from that group
        if group_id:
            from apps.students.models import StudentGroupEnrollment
            enrollments = StudentGroupEnrollment.objects.filter(
                group_id=group_id,
                is_active=True
            ).select_related('student')
            phone_numbers = [e.student.parent_phone for e in enrollments if e.student.parent_phone]

        if not phone_numbers:
            return JsonResponse({
                'success': False,
                'error': 'لا توجد أرقام للإرسال'
            }, status=400)

        whatsapp_service = WhatsAppService()
        result = whatsapp_service.send_bulk_message(phone_numbers, message)

        return JsonResponse({
            'success': True,
            'message': f'تم الإرسال: {result["success_count"]} ناجح / {result["fail_count"]} فاشل',
            'details': result
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

