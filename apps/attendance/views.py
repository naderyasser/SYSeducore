import json
import logging

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django_ratelimit.decorators import ratelimit

from apps.accounts.decorators import (
    ajax_login_required,
    ajax_supervisor_required,
    supervisor_required,
    ratelimit_key,
)
from .models import Session, Attendance, ActivityLog
from .services import AttendanceService

logger = logging.getLogger('attendance')

#: Generic message returned instead of the raw exception text — the internal
#: message leaks model names, SQL fragments and file paths to the client.
SERVER_ERROR_MESSAGE = 'حدث خطأ في النظام، يرجى المحاولة مرة أخرى'


@login_required
def scanner_page(request):
    """
    صفحة إدخال كود الطالب (النظام الجديد)
    """
    return render(request, 'attendance/scanner.html', {
        'page_title': 'تسجيل الحضور - إدخال يدوي'
    })


@ajax_login_required
@ratelimit(key=ratelimit_key, rate='30/m', block=False)
@require_http_methods(["POST"])
def process_student_code(request):
    """
    API Endpoint: معالجة كود الطالب

    النظام الجديد: استقبال كود الطالب يدوياً بدلاً من الباركود
    الخوارزمية: 4 خطوات صارمة
    """
    # block=False (above) lets us return the scanner's own JSON 429 contract
    # instead of django_ratelimit raising Ratelimited — a PermissionDenied
    # subclass that Django renders as an HTML 403, which the scanner's
    # `response.status === 429` branch can never see.
    if getattr(request, 'limited', False):
        return JsonResponse({
            'success': False,
            'message': 'تم تجاوز الحد المسموح من الطلبات، انتظر قليلاً',
            'sound': 'error'
        }, status=429)

    try:
        # قراءة البيانات من الطلب
        data = json.loads(request.body)
        student_code = data.get('student_code', '').strip()

        if not student_code:
            return JsonResponse({
                'success': False,
                'message': 'الرجاء إدخال كود الطالب',
                'sound': 'error'
            })

        # معالجة الكود باستخدام الخدمة الجديدة
        result = AttendanceService.process_scan(
            student_code=student_code,
            supervisor=request.user
        )

        return JsonResponse(result)

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'خطأ في البيانات المرسلة',
            'sound': 'error'
        })
    except Exception:
        logger.exception('process_student_code failed')
        return JsonResponse({
            'success': False,
            'message': SERVER_ERROR_MESSAGE,
            'sound': 'error'
        })


#: ``date.weekday()`` -> the English day names stored on ``GroupSchedule``.
_WEEKDAY_NAMES = [
    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
]


@login_required
def session_detail(request, session_id):
    """
    تفاصيل الحصة
    """
    session = get_object_or_404(Session, pk=session_id)
    attendances = session.attendances.select_related('student').all()

    # The group's own day for this session, not the legacy first-day column —
    # a group meeting several days a week has a different time on each.
    day_name = _WEEKDAY_NAMES[session.session_date.weekday()]
    schedule_entry = session.group.get_schedule_for_day(day_name)

    return render(request, 'attendance/session_detail.html', {
        'session': session,
        'attendances': attendances,
        'schedule_entry': schedule_entry,
    })


@ajax_supervisor_required
@require_http_methods(["POST"])
def record_teacher_attendance(request, session_id):
    """
    تسجيل حضور المدرس — عملية مكتبية: مشرف أو مدير فقط.
    """
    try:
        session = Session.objects.select_related('group').get(pk=session_id)
    except Session.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)

    session.teacher_attended = True
    session.teacher_checkin_time = timezone.now()
    session.save(update_fields=['teacher_attended', 'teacher_checkin_time'])

    ActivityLog.log(
        user=request.user,
        action='teacher_checkin',
        description=(
            f'تسجيل حضور المدرس لحصة {session.group.group_name} '
            f'بتاريخ {session.session_date}'
        ),
        target_model='Session',
        target_id=session.pk,
        request=request,
    )

    return JsonResponse({'success': True})


@ajax_supervisor_required
@require_http_methods(["POST"])
def cancel_session(request, session_id):
    """
    إلغاء حصة — عملية مكتبية: مشرف أو مدير فقط، وتُسجَّل في سجل النشاط
    حتى يمكن معرفة من ألغى الحصة ولماذا.
    """
    try:
        session = Session.objects.select_related('group').get(pk=session_id)
    except Session.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)

    reason = request.POST.get('reason', '')

    session.is_cancelled = True
    session.cancellation_reason = reason
    session.save(update_fields=['is_cancelled', 'cancellation_reason'])

    ActivityLog.log(
        user=request.user,
        action='session_cancel',
        description=(
            f'إلغاء حصة {session.group.group_name} بتاريخ {session.session_date}'
            + (f' — السبب: {reason}' if reason else '')
        ),
        target_model='Session',
        target_id=session.pk,
        request=request,
    )

    return JsonResponse({'success': True})


@ajax_login_required
@require_http_methods(["GET"])
def today_stats(request):
    """
    API Endpoint: إحصائيات الحضور اليوم
    """
    from datetime import timedelta

    try:
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)

        # حضور اليوم
        today_attendances = Attendance.objects.filter(
            session__session_date=today,
            status__in=['present', 'late']
        ).count()

        # حضور الأمس
        yesterday_attendances = Attendance.objects.filter(
            session__session_date=yesterday,
            status__in=['present', 'late']
        ).count()

        # التغيير
        change = today_attendances - yesterday_attendances

        # الحصص اليوم
        today_sessions = Session.objects.filter(
            session_date=today,
            is_cancelled=False,
            group__is_active=True  # Filter inactive groups
        ).count()

        # إجمالي الطلاب النشطين
        from apps.students.models import Student
        total_students = Student.objects.filter(is_active=True).count()

        return JsonResponse({
            'success': True,
            'present': today_attendances,
            'total': total_students,
            'sessions': today_sessions,
            'change': change
        })

    except Exception:
        logger.exception('today_stats failed')
        return JsonResponse({
            'success': False,
            'error': SERVER_ERROR_MESSAGE
        }, status=500)


@ajax_login_required
@require_http_methods(["GET"])
def today_sessions(request):
    """
    API Endpoint: حصص اليوم مع عدد الحضور

    نقطة قراءة فقط — كانت تُنشئ صف ``Session`` لكل مجموعة في كل استعلام
    تحديث للوحة (كل بضع ثوانٍ). الحصة تُنشأ عند أول مسح حضور.
    """
    from django.db.models import Count, Q

    try:
        today = timezone.localdate()
        day_name = AttendanceService.get_current_day_name()
        from apps.teachers.models import Group

        # جلب المجموعات التي لها حصص اليوم (كل أيام GroupSchedule وليس
        # اليوم الأول فقط من الحقول القديمة)
        groups = (
            Group.objects.filter(is_active=True)
            .select_related('teacher')
            .prefetch_related('schedules')
        )

        # الحصص الموجودة فعلاً اليوم مع عدد الحضور — استعلام واحد
        sessions_today = {
            s.group_id: s
            for s in Session.objects.filter(session_date=today).annotate(
                attendees_count=Count(
                    'attendances',
                    filter=Q(attendances__status__in=['present', 'late']),
                )
            )
        }

        scheduled = []
        for group in groups:
            entry = group.get_schedule_for_day(day_name)
            if entry is None or not entry.start_time:
                continue

            session = sessions_today.get(group.pk)
            scheduled.append((entry.start_time, {
                'session_id': session.session_id if session else None,
                'group_name': group.group_name,
                'time': entry.start_time.strftime('%I:%M %p'),
                'teacher_name': group.teacher.full_name if group.teacher else None,
                'attendees': session.attendees_count if session else 0,
                'is_active': True
            }))

        scheduled.sort(key=lambda item: item[0])
        sessions_data = [item[1] for item in scheduled]

        return JsonResponse({
            'success': True,
            'sessions': sessions_data
        })

    except Exception:
        logger.exception('today_sessions failed')
        return JsonResponse({
            'success': False,
            'error': SERVER_ERROR_MESSAGE
        }, status=500)


@supervisor_required
@require_http_methods(["GET"])
def export_report(request):
    """
    تصدير تقرير الحضور — ملف CSV حقيقي للتحميل المباشر.

    كان POST يُرجع محتوى CSV كنص JSON بلا BOM (فيظهر العربي مشفّرًا في
    إكسل) ثم JavaScript يبنى منه Blob — الآن GET يُرجع ملفًا فعليًا
    برأسية ``utf-8-sig`` فيعمل رابط تحميل مباشر (``<a href>``) بلا CSRF
    ولا fetch. تصدير كل حضور السنتر ليس بيانات مدرس، فرُفع من
    ``@ajax_login_required`` إلى ``@supervisor_required``.
    """
    report_date = request.GET.get('date')
    report_type = request.GET.get('type', 'summary')

    if not report_date:
        return JsonResponse({'success': False, 'message': 'التاريخ مطلوب'}, status=400)

    from datetime import datetime
    try:
        report_date_obj = datetime.strptime(report_date, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'success': False, 'message': 'صيغة التاريخ غير صحيحة'}, status=400)

    attendances = Attendance.objects.filter(
        session__session_date=report_date_obj
    ).select_related('student', 'session__group', 'session__group__teacher').order_by('-scan_time')

    import csv

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="attendance_{report_date}.csv"'
    # utf-8-sig on the content-type covers the encoding, but Django's
    # HttpResponse writer needs the literal BOM bytes at the start of the
    # body too — Excel keys off this, not the header, to detect UTF-8.
    response.write('﻿')
    writer = csv.writer(response)

    if not attendances.exists():
        writer.writerow(['لا توجد بيانات لهذا التاريخ', report_date])
        return response

    if report_type == 'summary':
        writer.writerow(['تقرير حضور مختصر', report_date])
        writer.writerow([])
        writer.writerow(['إجمالي الحضور', attendances.filter(status='present').count()])
        writer.writerow(['عدد المتأخرين', attendances.filter(status='late').count()])
        writer.writerow(['عدد الغياب', attendances.filter(status='absent').count()])

    elif report_type == 'detailed':
        writer.writerow(['تقرير حضور تفصيلي', report_date])
        writer.writerow([])
        writer.writerow(['اسم الطالب', 'كود الطالب', 'المجموعة', 'المعلم', 'الحالة', 'وقت المسح'])
        for att in attendances:
            writer.writerow([
                att.student.full_name,
                att.student.student_code,
                att.session.group.group_name,
                att.session.group.teacher.full_name if att.session.group.teacher else '-',
                att.get_status_display(),
                timezone.localtime(att.scan_time).strftime('%I:%M %p')
            ])

    elif report_type == 'students':
        writer.writerow(['قائمة الطلاب المسجلين', report_date])
        writer.writerow([])
        writer.writerow(['اسم الطالب', 'كود الطالب', 'المجموعة', 'الحالة', 'وقت المسح'])
        for att in attendances:
            writer.writerow([
                att.student.full_name,
                att.student.student_code,
                att.session.group.group_name,
                att.get_status_display(),
                timezone.localtime(att.scan_time).strftime('%I:%M %p')
            ])

    return response


# ─────────────────────────────────────────────────────────────
# Scanner Quick-Action APIs  (Pay Now / Grace Period)
# ─────────────────────────────────────────────────────────────

def _resolve_scanner_payment(student, group_id=None):
    """
    Pick the Payment row the scanner's "ادفع الان" button should settle.

    Preference order: the group the scanner asked about, then the first active
    enrollment that still owes money on its **current cycle**, then the first
    active enrollment. Blindly taking the *first* enrollment charged the
    wrong group for a student enrolled in several.

    Money is per (student, group) via that group's open
    :class:`~apps.teachers.models.GroupCycle` — never by calendar month, so
    two cycles closing inside one month never collide.

    Returns ``(payment, error_message)``.
    """
    from apps.payments.models import Payment
    from apps.payments.pricing import prorated_fee
    from apps.students.models import StudentGroupEnrollment
    from apps.teachers.cycles import open_cycle_for

    enrollments = list(
        StudentGroupEnrollment.objects.filter(
            student=student,
            is_active=True,
            group__is_active=True,
            group__deleted_at__isnull=True,
        )
        .select_related('group')
    )
    if not enrollments:
        return None, 'لا يوجد تسجيل نشط'

    if group_id:
        enrollments = [e for e in enrollments if str(e.group_id) == str(group_id)] or enrollments

    cycles_by_group = {
        enr.group_id: open_cycle_for(enr.group)
        for enr in enrollments if enr.group.sessions_per_month
    }
    payments = {
        p.group_id: p
        for p in Payment.objects.filter(
            student=student,
            cycle_id__in=[c.cycle_id for c in cycles_by_group.values()],
        )
    }

    for enr in enrollments:
        payment = payments.get(enr.group_id)
        if payment is None or payment.status != 'paid':
            if payment is not None:
                return payment, None
            cycle = cycles_by_group.get(enr.group_id)
            if cycle is None:
                continue  # group is not cycle-billed at all — nothing to collect
            fee = prorated_fee(
                enr, cycle_size=cycle.sessions_planned, first_sequence=1, group=enr.group,
            )
            payment, _ = Payment.objects.get_or_create(
                student=student, group=enr.group, cycle=cycle,
                defaults={
                    'amount_due': fee, 'status': 'unpaid',
                    'month': (cycle.started_on or timezone.localdate()).replace(day=1),
                    'sessions_total': cycle.sessions_planned,
                },
            )
            return payment, None

    if not payments:
        return None, 'لا يوجد مستحقات لهذا الطالب'
    # Everything is already settled — return the first row so the caller gets
    # an idempotent success instead of a confusing error.
    first_with_payment = next((e for e in enrollments if e.group_id in payments), enrollments[0])
    return payments.get(first_with_payment.group_id) or next(iter(payments.values())), None


@ajax_supervisor_required
@require_http_methods(["POST"])
def scanner_pay_now(request):
    """
    Called from the scanner UI when the supervisor taps "ادفع الان".
    Marks this cycle's payment as paid and re-activates the enrollment for
    this group only — never touches any other group the student is in.

    Moves money, so it is restricted to admin/supervisor, written to the
    activity log ("who marked this paid?") and applied atomically.
    """
    import json as _json
    from datetime import date as _date
    from apps.payments.models import Payment
    from apps.payments.activation import activate_payment

    try:
        body = _json.loads(request.body) if request.content_type == 'application/json' else request.POST
        payment_id = body.get('payment_id')
        student_id = body.get('student_id')
        group_id = body.get('group_id')
        raw_paid_on = body.get('paid_on')
        try:
            paid_on = _date.fromisoformat(raw_paid_on) if raw_paid_on else None
        except ValueError:
            paid_on = None

        if payment_id:
            payment = Payment.objects.select_related('student', 'group').get(pk=payment_id)
        elif student_id:
            from apps.students.models import Student
            student = Student.objects.get(pk=student_id)
            payment, error = _resolve_scanner_payment(student, group_id)
            if error:
                return JsonResponse({'success': False, 'message': error}, status=400)
        else:
            return JsonResponse({'success': False, 'message': 'payment_id أو student_id مطلوب'}, status=400)

        with transaction.atomic():
            # Settle through the payment ledger so the movement leaves a
            # receipt row with its author, instead of overwriting amount_paid.
            payment.settle_full(
                user=request.user, note='تسديد من الماسح الضوئي', effective_on=paid_on,
            )

            # Re-activate the enrollment for THIS group only.
            activate_payment(payment, paid_on=paid_on, user=request.user, request=request)

            ActivityLog.log(
                user=request.user,
                action='payment_record',
                description=(
                    f'تسديد من الماسح: {payment.student.full_name} — '
                    f'{payment.group.group_name} — شهر {payment.month:%Y-%m} — '
                    f'{payment.amount_due} ج.م'
                ),
                target_model='Payment',
                target_id=payment.pk,
                request=request,
            )

        return JsonResponse({
            'success': True,
            'message': 'تم تسديد الدفعة وتفعيل الاشتراك بنجاح',
        })
    except Payment.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'سجل الدفع غير موجود'}, status=404)
    except Exception:
        logger.exception('scanner_pay_now failed')
        return JsonResponse({'success': False, 'message': SERVER_ERROR_MESSAGE}, status=500)


@ajax_supervisor_required
@require_http_methods(["POST"])
def scanner_grace_period(request):
    """
    Called from the scanner UI when the supervisor taps "استثناء".
    Sets a grace_until date on the *active* enrollments so the student can
    attend for X days WITHOUT changing their payment status.

    It deliberately does **not** resurrect enrollments the desk has removed:
    granting a payment grace period is not the same decision as putting a
    student back into a group they were taken out of.
    """
    import json as _json
    from datetime import timedelta
    from apps.students.models import Student, StudentGroupEnrollment

    try:
        body = _json.loads(request.body) if request.content_type == 'application/json' else request.POST
        student_id = body.get('student_id')
        group_id = body.get('group_id')

        try:
            days = int(body.get('days', 3))
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'عدد الأيام غير صالح'}, status=400)
        if days < 1 or days > 90:
            return JsonResponse(
                {'success': False, 'message': 'عدد الأيام يجب أن يكون بين 1 و 90'}, status=400
            )

        if not student_id:
            return JsonResponse({'success': False, 'message': 'student_id مطلوب'}, status=400)

        student = Student.objects.get(pk=student_id)

        today = timezone.localdate()
        grace_date = today + timedelta(days=days)

        with transaction.atomic():
            # Grace is scoped to (student × group) only — it must never touch
            # any other group this student is enrolled in. It used to extend
            # a global ``subscription_expiry_date``, so a 3-day grace for one
            # teacher silently granted 3 free days everywhere.
            enrollments = StudentGroupEnrollment.objects.filter(
                student=student, is_active=True,
            )
            if group_id:
                enrollments = enrollments.filter(group_id=group_id)
            updated = enrollments.update(grace_until=grace_date)

            ActivityLog.log(
                user=request.user,
                action='override_financial',
                description=(
                    f'منح مهلة {days} أيام لـ {student.full_name} '
                    f'حتى {grace_date} ({updated} تسجيل)'
                ),
                target_model='Student',
                target_id=student.pk,
                request=request,
            )

        return JsonResponse({
            'success': True,
            'message': f'تم منح مهلة {days} أيام لـ {student.full_name} (حتى {grace_date})',
            'days': days,
            'grace_until': grace_date.isoformat(),
        })
    except Student.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'الطالب غير موجود'}, status=404)
    except Exception:
        logger.exception('scanner_grace_period failed')
        return JsonResponse({'success': False, 'message': SERVER_ERROR_MESSAGE}, status=500)


@ajax_supervisor_required
@require_http_methods(["POST"])
def grant_exception(request):
    """
    Grant an exception (payment or late-arrival) for a student.
    Called from the scanner UI by admin/supervisor — now actually enforced.

    Request body:
    - student_id
    - group_id (optional)
    - session_id (optional, for late-arrival context)
    - exception_type: 'payment' or 'late_arrival'
    - reason_type: one of the predefined reasons
    - custom_reason: free text (optional)
    """
    import json as _json
    from apps.students.models import Student
    from apps.teachers.models import Group
    from .models import ExceptionRecord, Session as SessionModel

    try:
        body = _json.loads(request.body) if request.content_type == 'application/json' else request.POST
        student_id = body.get('student_id')
        group_id = body.get('group_id')
        session_id = body.get('session_id')
        exception_type = body.get('exception_type') or 'payment'
        reason_type = body.get('reason_type') or 'other'
        custom_reason = body.get('custom_reason', '')

        if not student_id:
            return JsonResponse({'success': False, 'message': 'student_id مطلوب'}, status=400)

        # ``choices`` are not enforced by the database, so validate here or
        # arbitrary strings end up stored and rendered back to the user.
        valid_types = dict(ExceptionRecord.EXCEPTION_TYPE_CHOICES)
        if exception_type not in valid_types:
            return JsonResponse(
                {'success': False, 'message': 'نوع الاستثناء غير صالح'}, status=400
            )
        valid_reasons = dict(ExceptionRecord.PREDEFINED_REASON_CHOICES)
        if reason_type not in valid_reasons:
            return JsonResponse(
                {'success': False, 'message': 'سبب الاستثناء غير صالح'}, status=400
            )

        student = Student.objects.get(pk=student_id)
        group = None
        if group_id:
            group = Group.objects.get(pk=group_id)

        session = None
        if session_id:
            session = SessionModel.objects.filter(pk=session_id).first()

        with transaction.atomic():
            # Create exception record
            exception = ExceptionRecord.objects.create(
                student=student,
                group=group,
                session=session,
                exception_type=exception_type,
                reason_type=reason_type,
                custom_reason=custom_reason,
                approved_by=request.user,
            )

            # If this is a late_arrival exception and we have a session,
            # immediately apply it by marking attendance as 'exception'
            if exception_type == 'late_arrival' and session and group:
                AttendanceService.apply_late_exception(student, group, session, exception)

            # Log the action
            ActivityLog.log(
                user=request.user,
                action='exception_grant',
                description=(
                    f'منح استثناء {student.full_name}: '
                    f'{exception.get_exception_type_display()} — {exception.reason_display}'
                ),
                target_model='ExceptionRecord',
                target_id=exception.pk,
                request=request,
            )

        # Dispatch WhatsApp notification (fire-and-forget via Celery)
        try:
            from .tasks import send_exception_notification
            group_name = group.group_name if group else '—'
            send_exception_notification.delay(
                student_id=student.student_id,
                group_name=group_name,
                exception_type=exception_type,
                reason_display=exception.reason_display,
            )
        except Exception:
            # Celery may not be available; the notification is non-critical,
            # but a silent swallow hid broker outages completely.
            logger.warning(
                'Could not queue exception notification for student %s',
                student.pk, exc_info=True,
            )

        return JsonResponse({
            'success': True,
            'message': f'تم منح استثناء لـ {student.full_name}',
            'exception': {
                'exception_id': exception.exception_id,
                'type': exception_type,
                'reason': exception.reason_display,
            },
        })

    except Student.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'الطالب غير موجود'}, status=404)
    except Group.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'المجموعة غير موجودة'}, status=404)
    except Exception:
        logger.exception('grant_exception failed')
        return JsonResponse({'success': False, 'message': SERVER_ERROR_MESSAGE}, status=500)


@ajax_login_required
@require_http_methods(["GET"])
def exception_reasons_list(request):
    """
    Return the predefined exception reasons list for the frontend dropdown.
    """
    from .models import ExceptionRecord
    reasons = [
        {'value': value, 'label': label}
        for value, label in ExceptionRecord.PREDEFINED_REASON_CHOICES
    ]
    return JsonResponse({'success': True, 'reasons': reasons})


@ajax_supervisor_required
@require_http_methods(["POST"])
def revoke_exception(request, exception_id):
    """
    Revoke (deactivate) an exception. The exception remains in the log
    but is marked inactive so it won't be considered for future scans.
    Admin/supervisor only, same as granting one.
    """
    from .models import ExceptionRecord

    try:
        exception = ExceptionRecord.objects.select_related('student').get(pk=exception_id)
        exception.is_active = False
        exception.save(update_fields=['is_active'])

        ActivityLog.log(
            user=request.user,
            action='exception_revoke',
            description=f'إلغاء استثناء {exception.student.full_name}: {exception.reason_display}',
            target_model='ExceptionRecord',
            target_id=exception.pk,
            request=request,
        )

        return JsonResponse({
            'success': True,
            'message': f'تم إلغاء الاستثناء لـ {exception.student.full_name}',
        })
    except ExceptionRecord.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'الاستثناء غير موجود'}, status=404)
