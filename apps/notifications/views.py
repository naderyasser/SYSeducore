import json
import logging
import uuid
from datetime import datetime
from functools import wraps

from django.conf import settings
from django.contrib import messages as django_messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import ajax_supervisor_required, supervisor_required
from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.models import Group

from .forms import BulkWhatsAppForm, SendWhatsAppMessageForm
from .models import WhatsAppMessage, WhatsAppTemplate
from .services import WhatsAppService
from .tasks import send_bulk_attendance_report_task, send_bulk_whatsapp_task

logger = logging.getLogger('notifications')

#: AUTH-12 — every view in this module used to be authentication-only, so any
#: logged-in account (a teacher, say) could WhatsApp every parent in the centre
#: with an arbitrary body. Messaging is a desk operation: admin or supervisor.
WHATSAPP_DISABLED_MESSAGE = 'خدمة الواتساب معطلة حالياً'
GENERIC_ERROR_MESSAGE = 'حدث خطأ أثناء تنفيذ العملية، يرجى المحاولة مرة أخرى'
QUEUE_FAILED_MESSAGE = 'تعذر جدولة الإرسال حالياً، يرجى المحاولة لاحقاً'
#: contact_list used to render every active student on one page.
CONTACTS_PER_PAGE = 50


def whatsapp_required(view_func):
    """Block access to WhatsApp views when notifications are disabled."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if getattr(settings, 'NOTIFICATION_METHOD', 'none') != 'whatsapp':
            django_messages.warning(request, WHATSAPP_DISABLED_MESSAGE)
            return redirect('reports:dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


def whatsapp_required_ajax(view_func):
    """``whatsapp_required`` for fetch() endpoints: JSON, never a redirect."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if getattr(settings, 'NOTIFICATION_METHOD', 'none') != 'whatsapp':
            return JsonResponse(
                {'success': False, 'error': WHATSAPP_DISABLED_MESSAGE}, status=503
            )
        return view_func(request, *args, **kwargs)
    return _wrapped


def _queue_bulk_send(**kwargs):
    """
    Hand a bulk send to Celery (PERF-03) and report whether it was accepted.

    Bulk sending must never happen in the request thread: each message is a
    blocking HTTP call with a 10 s timeout, so 100 recipients outlive
    gunicorn's 120 s limit and the worker is killed with the batch half sent.
    """
    try:
        send_bulk_whatsapp_task.delay(**kwargs)
        return True
    except Exception:
        logger.exception('Could not queue bulk WhatsApp send')
        return False


@supervisor_required
@whatsapp_required
def whatsapp_dashboard(request):
    """
    لوحة تحكم إدارة الواتساب
    """
    # إحصائيات الرسائل — التاريخ المحلي وليس UTC
    today_messages = WhatsAppMessage.objects.filter(
        created_at__date=timezone.localdate()
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


@supervisor_required
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
                    # إرسال لجميع طلاب المجموعة — في الخلفية عبر Celery (PERF-03)
                    enrollments = StudentGroupEnrollment.objects.filter(
                        group=group,
                        is_active=True,
                        student__deleted_at__isnull=True,
                        student__is_active=True,
                    ).select_related('student')

                    recipients = []
                    for enrollment in enrollments:
                        student_obj = enrollment.student
                        phone = (student_obj.parent_phone or '').strip()
                        if not phone:
                            continue
                        final_message = message_text
                        if include_name:
                            final_message = (
                                f"أولياء أمور الطالب {student_obj.full_name}\n\n{message_text}"
                            )
                        recipients.append({
                            'phone': phone,
                            'student_id': student_obj.pk,
                            'message': final_message,
                        })

                    if not recipients:
                        django_messages.error(request, 'لا توجد أرقام للإرسال في هذه المجموعة')
                    elif _queue_bulk_send(
                        recipients=recipients,
                        message=message_text,
                        batch_key=uuid.uuid4().hex,
                        sent_by_id=request.user.pk,
                        group_id=group.pk,
                        message_type='group',
                    ):
                        django_messages.success(
                            request,
                            f'تمت جدولة إرسال {len(recipients)} رسالة، '
                            f'تابع الحالة في سجل الرسائل',
                        )
                    else:
                        django_messages.error(request, QUEUE_FAILED_MESSAGE)

                return redirect('notifications:whatsapp_dashboard')

            except Exception:
                # QUAL-01: the raw exception text leaked model names, SQL
                # fragments and file paths to the browser.
                logger.exception('WhatsApp send_message failed')
                django_messages.error(request, GENERIC_ERROR_MESSAGE)

    else:
        initial = {}
        if request.GET.get('student'):
            initial['student'] = request.GET.get('student')
        if request.GET.get('type'):
            initial['recipient_type'] = request.GET.get('type')
        form = SendWhatsAppMessageForm(initial=initial)

    context = {
        'form': form,
        'page_title': 'إرسال رسالة واتساب'
    }
    return render(request, 'notifications/send_message.html', context)


@supervisor_required
@whatsapp_required
def send_bulk_message(request):
    """
    صفحة الإرسال الجماعي

    PERF-03: the request only *queues* the batch. Sending 100 messages inline
    meant ~1000 s of blocking HTTP calls — the gunicorn worker was killed long
    before that with the batch half delivered and no record of where it got to.
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

                group = form.cleaned_data.get('group')
                recipients = []

                if bulk_type == 'group':
                    recipient_role = form.cleaned_data.get('recipient_role', 'parent')

                    enrollments = StudentGroupEnrollment.objects.filter(
                        group=group,
                        is_active=True,
                        student__deleted_at__isnull=True,
                        student__is_active=True,
                    ).select_related('student')

                    for enrollment in enrollments:
                        student = enrollment.student
                        parent_phone = (student.parent_phone or '').strip()
                        student_phone = (student.student_phone or '').strip()

                        if recipient_role in ('parent', 'both') and parent_phone:
                            recipients.append(
                                {'phone': parent_phone, 'student_id': student.pk}
                            )
                        if recipient_role in ('student', 'both') and student_phone:
                            recipients.append(
                                {'phone': student_phone, 'student_id': student.pk}
                            )

                elif bulk_type == 'custom_list':
                    phone_numbers = form.cleaned_data['phone_numbers'] or ''
                    for phone in phone_numbers.replace('\r', '').split('\n'):
                        phone = phone.strip()
                        if phone:
                            recipients.append({'phone': phone})

                elif bulk_type == 'attendance_report':
                    if not group:
                        django_messages.error(request, 'اختر مجموعة')
                        return redirect('notifications:send_bulk_message')
                    try:
                        send_bulk_attendance_report_task.delay(
                            group_id=group.pk,
                            batch_key=uuid.uuid4().hex,
                            sent_by_id=request.user.pk,
                        )
                        django_messages.success(
                            request, 'تمت جدولة إرسال تقرير الحضور، تابع الحالة في سجل الرسائل'
                        )
                    except Exception:
                        logger.exception('Could not queue attendance report')
                        django_messages.error(request, QUEUE_FAILED_MESSAGE)
                    return redirect('notifications:whatsapp_dashboard')

                if not recipients:
                    django_messages.error(request, 'لا توجد أرقام للإرسال')
                elif _queue_bulk_send(
                    recipients=recipients,
                    message=message_text,
                    batch_key=uuid.uuid4().hex,
                    sent_by_id=request.user.pk,
                    group_id=group.pk if (bulk_type == 'group' and group) else None,
                    # 'custom_list' is not a WhatsAppMessage type — it used to be
                    # written straight into the column as an invalid choice.
                    message_type='group' if bulk_type == 'group' else 'custom',
                ):
                    django_messages.success(
                        request,
                        f'تمت جدولة إرسال {len(recipients)} رسالة، '
                        f'تابع الحالة في سجل الرسائل',
                    )
                else:
                    django_messages.error(request, QUEUE_FAILED_MESSAGE)

                return redirect('notifications:whatsapp_dashboard')

            except Exception:
                # QUAL-01: no raw exception text in the response.
                logger.exception('WhatsApp send_bulk_message failed')
                django_messages.error(request, GENERIC_ERROR_MESSAGE)

    else:
        form = BulkWhatsAppForm()

    context = {
        'form': form,
        'page_title': 'الإرسال الجماعي'
    }
    return render(request, 'notifications/send_bulk_message.html', context)


@supervisor_required
@whatsapp_required
def message_history(request):
    """
    سجل الرسائل المرسلة
    """
    messages_query = WhatsAppMessage.objects.select_related('student', 'sent_by')

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
        # 'whatsapp_messages', not 'messages' — the latter key is owned by
        # django.contrib.messages' context processor (base.html's flash
        # banners); shadowing it hid every real success/error message and
        # rendered one bogus alert per row instead.
        'whatsapp_messages': messages_query[:100],  # آخر 100 رسالة
        'stats': stats,
        'status_filter': status,
        'type_filter': msg_type,
        'search_query': search,
        'page_title': 'سجل الرسائل'
    }

    return render(request, 'notifications/message_history.html', context)


@supervisor_required
@whatsapp_required
def contact_list(request):
    """
    قائمة جهات الاتصال (الطلاب وأولياء الأمور)
    """
    contact_type = request.GET.get('type', 'all')  # all, student, parent

    # BUG-11: ``student_phone`` / ``parent_phone`` are ``blank=True`` **without**
    # ``null=True``, i.e. NOT NULL columns — ``__isnull=False`` matched every
    # single row, so both filters were no-ops. A missing number is ``''``.
    if contact_type == 'student':
        contacts = Student.objects.filter(is_active=True).exclude(student_phone='')
    elif contact_type == 'parent':
        contacts = Student.objects.filter(is_active=True).exclude(parent_phone='')
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

    # An unfiltered visit used to serialise the whole active-student table
    # into one page (plus a separate COUNT for {{ contacts.count }}) — cap
    # and paginate like every other listing view.
    total_contacts = contacts.count()
    paginator = Paginator(contacts, CONTACTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'contacts': page_obj,
        'total_contacts': total_contacts,
        'contact_type': contact_type,
        'search_query': search,
        'page_title': 'قائمة جهات الاتصال'
    }

    return render(request, 'notifications/contact_list.html', context)


@supervisor_required
@whatsapp_required
def manage_templates(request):
    """
    إدارة قوالب الرسائل
    """
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            name = request.POST.get('name')
            # description is TextField(blank=True) — NOT NULL. The shipped
            # form always posts an (empty) textarea, but a raw POST/API
            # client that omits the key sends None, which IntegrityErrors.
            description = request.POST.get('description') or ''
            message_text = request.POST.get('message_text')

            if name and message_text and len(name) > 100:
                django_messages.error(request, 'اسم القالب طويل جداً (الحد الأقصى 100 حرف)')
            elif name and message_text:
                WhatsAppTemplate.objects.create(
                    name=name,
                    description=description,
                    message_text=message_text
                )
                django_messages.success(request, f'تم إنشاء القالب "{name}" بنجاح')
            else:
                django_messages.error(request, 'الاسم والنص مطلوبان')

        elif action == 'update':
            template_id = request.POST.get('template_id')
            name = request.POST.get('name')
            description = request.POST.get('description') or ''
            message_text = request.POST.get('message_text')
            try:
                template = WhatsAppTemplate.objects.get(pk=template_id)
            except (WhatsAppTemplate.DoesNotExist, ValueError, TypeError):
                django_messages.error(request, 'القالب غير موجود')
            else:
                if not (name and message_text):
                    django_messages.error(request, 'الاسم والنص مطلوبان')
                elif len(name) > 100:
                    django_messages.error(request, 'اسم القالب طويل جداً (الحد الأقصى 100 حرف)')
                else:
                    template.name = name
                    template.description = description
                    template.message_text = message_text
                    template.save(update_fields=['name', 'description', 'message_text', 'updated_at'])
                    django_messages.success(request, f'تم تحديث القالب "{name}" بنجاح')

        elif action == 'delete':
            template_id = request.POST.get('template_id')
            try:
                template = WhatsAppTemplate.objects.get(pk=template_id)
                template.delete()
                django_messages.success(request, 'تم حذف القالب بنجاح')
            except (WhatsAppTemplate.DoesNotExist, ValueError, TypeError):
                django_messages.error(request, 'القالب غير موجود')

        return redirect('notifications:manage_templates')

    templates = WhatsAppTemplate.objects.all()

    context = {
        'templates': templates,
        'page_title': 'إدارة قوالب الرسائل'
    }

    return render(request, 'notifications/manage_templates.html', context)


@ajax_supervisor_required
@whatsapp_required_ajax
@require_http_methods(["POST"])
def send_bulk_attendance_report(request):
    """
    API: جدولة إرسال تقرير حضور/غياب جماعي عبر الواتساب

    PERF-03: the report is built and delivered by a Celery worker; the request
    returns as soon as the batch is queued.
    """
    try:
        data = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'صيغة الطلب غير صحيحة'}, status=400)

    group_id = data.get('group_id')
    session_date = data.get('session_date')  # Optional YYYY-MM-DD

    if not group_id:
        return JsonResponse(
            {'success': False, 'error': 'معرف المجموعة مطلوب'}, status=400
        )

    try:
        group_id = int(group_id)
    except (TypeError, ValueError):
        return JsonResponse(
            {'success': False, 'error': 'المجموعة غير موجودة'}, status=404
        )

    if not Group.objects.filter(pk=group_id).exists():
        return JsonResponse(
            {'success': False, 'error': 'المجموعة غير موجودة'}, status=404
        )

    if session_date:
        try:
            datetime.strptime(str(session_date), '%Y-%m-%d')
        except (TypeError, ValueError):
            return JsonResponse(
                {'success': False, 'error': 'صيغة التاريخ غير صحيحة'}, status=400
            )

    batch_key = uuid.uuid4().hex
    try:
        send_bulk_attendance_report_task.delay(
            group_id=group_id,
            session_date=session_date,
            batch_key=batch_key,
            sent_by_id=request.user.pk,
        )
    except Exception:
        # QUAL-01: log the detail, tell the client nothing about our internals.
        logger.exception('Could not queue attendance report for group %s', group_id)
        return JsonResponse({'success': False, 'error': QUEUE_FAILED_MESSAGE}, status=503)

    return JsonResponse({
        'success': True,
        'status': 'queued',
        'batch_key': batch_key,
        'message': 'تمت جدولة إرسال التقرير، تابع الحالة في سجل الرسائل',
    })


@ajax_supervisor_required
@whatsapp_required_ajax
@require_http_methods(["POST"])
def send_bulk_custom_message(request):
    """
    API: جدولة إرسال رسالة مخصصة جماعية

    AUTH-12: this endpoint accepts a free-form list of phone numbers and an
    arbitrary body. It used to be authentication-only — any account could
    message every parent in the centre — and it did not even record what it
    sent. It is now admin/supervisor only, and every message is written to
    ``WhatsAppMessage`` by the Celery task (PERF-03) with the requesting user
    attached.
    """
    try:
        data = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'صيغة الطلب غير صحيحة'}, status=400)

    message = (data.get('message') or '').strip()
    group_id = data.get('group_id')  # Optional: send to all parents in group

    if not message:
        return JsonResponse({'success': False, 'error': 'نص الرسالة مطلوب'}, status=400)

    recipients = []
    if group_id:
        try:
            group_id = int(group_id)
        except (TypeError, ValueError):
            return JsonResponse(
                {'success': False, 'error': 'المجموعة غير موجودة'}, status=404
            )
        if not Group.objects.filter(pk=group_id).exists():
            return JsonResponse(
                {'success': False, 'error': 'المجموعة غير موجودة'}, status=404
            )
        enrollments = StudentGroupEnrollment.objects.filter(
            group_id=group_id,
            is_active=True,
            student__deleted_at__isnull=True,
            student__is_active=True,
        ).select_related('student')
        for enrollment in enrollments:
            phone = (enrollment.student.parent_phone or '').strip()
            if phone:
                recipients.append({'phone': phone, 'student_id': enrollment.student.pk})
    else:
        raw_numbers = data.get('phone_numbers') or []
        if isinstance(raw_numbers, str):
            raw_numbers = raw_numbers.replace('\r', '').split('\n')
        if not isinstance(raw_numbers, (list, tuple)):
            return JsonResponse(
                {'success': False, 'error': 'قائمة الأرقام غير صحيحة'}, status=400
            )
        for phone in raw_numbers:
            phone = str(phone or '').strip()
            if phone:
                recipients.append({'phone': phone})

    if not recipients:
        return JsonResponse({'success': False, 'error': 'لا توجد أرقام للإرسال'}, status=400)

    batch_key = uuid.uuid4().hex
    if not _queue_bulk_send(
        recipients=recipients,
        message=message,
        batch_key=batch_key,
        sent_by_id=request.user.pk,
        group_id=group_id or None,
        message_type='group' if group_id else 'custom',
    ):
        return JsonResponse({'success': False, 'error': QUEUE_FAILED_MESSAGE}, status=503)

    return JsonResponse({
        'success': True,
        'status': 'queued',
        'batch_key': batch_key,
        'queued': len(recipients),
        'message': f'تمت جدولة إرسال {len(recipients)} رسالة، تابع الحالة في سجل الرسائل',
    })
