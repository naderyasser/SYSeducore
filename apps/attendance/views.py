from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.accounts.decorators import ajax_login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
from .models import Session, Attendance
from .services import AttendanceService
from apps.students.models import Student
import json


@login_required
def scanner_page(request):
    """
    صفحة إدخال كود الطالب (النظام الجديد)
    """
    return render(request, 'attendance/scanner.html', {
        'page_title': 'تسجيل الحضور - إدخال يدوي'
    })


@ajax_login_required
@ratelimit(key='ip', rate='30/m', block=True)
@require_http_methods(["POST"])
def process_student_code(request):
    """
    API Endpoint: معالجة كود الطالب

    النظام الجديد: استقبال كود الطالب يدوياً بدلاً من الباركود
    الخوارزمية: 4 خطوات صارمة
    """
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
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'خطأ في النظام: {str(e)}',
            'sound': 'error'
        })


@login_required
def session_detail(request, session_id):
    """
    تفاصيل الحصة
    """
    session = get_object_or_404(Session, pk=session_id)
    attendances = session.attendances.select_related('student').all()
    return render(request, 'attendance/session_detail.html', {
        'session': session,
        'attendances': attendances
    })


@login_required
@require_http_methods(["POST"])
def record_teacher_attendance(request, session_id):
    """
    تسجيل حضور المدرس
    """
    try:
        session = Session.objects.get(pk=session_id)
        session.teacher_attended = True
        session.teacher_checkin_time = timezone.now()
        session.save()
        
        return JsonResponse({'success': True})
    except Session.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)


@login_required
@require_http_methods(["POST"])
def cancel_session(request, session_id):
    """
    إلغاء حصة
    """
    try:
        session = Session.objects.get(pk=session_id)
        reason = request.POST.get('reason', '')

        session.is_cancelled = True
        session.cancellation_reason = reason
        session.save()

        return JsonResponse({'success': True})
    except Session.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)


@ajax_login_required
@require_http_methods(["GET"])
def today_stats(request):
    """
    API Endpoint: إحصائيات الحضور اليوم
    """
    from django.db.models import Count, Q
    from django.utils import timezone
    from datetime import timedelta

    try:
        today = timezone.now().date()
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

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@ajax_login_required
@require_http_methods(["GET"])
def today_sessions(request):
    """
    API Endpoint: حصص اليوم مع عدد الحضور
    """
    from django.db.models import Count
    from django.utils import timezone

    try:
        today = timezone.now().date()
        from apps.teachers.models import Group

        # جلب المجموعات التي لها حصص اليوم
        groups = Group.objects.filter(
            schedule_day=AttendanceService.get_current_day_name(),
            is_active=True
        ).select_related('teacher', 'room')

        sessions_data = []
        for group in groups:
            # الحصول على حصة اليوم أو إنشاؤها
            session, created = Session.objects.get_or_create(
                group=group,
                session_date=today,
                defaults={'teacher_attended': False}
            )

            # عدد الحضور
            attendees_count = session.attendances.filter(
                status__in=['present', 'late']
            ).count()

            sessions_data.append({
                'session_id': session.session_id,
                'group_name': group.group_name,
                'time': group.schedule_time.strftime('%I:%M %p'),
                'teacher_name': group.teacher.full_name if group.teacher else None,
                'attendees': attendees_count,
                'is_active': True
            })

        return JsonResponse({
            'success': True,
            'sessions': sessions_data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@ajax_login_required
@require_http_methods(["POST"])
def export_report(request):
    """
    API Endpoint: تصدير تقرير الحضور
    """
    try:
        data = json.loads(request.body)
        report_date = data.get('date')
        report_type = data.get('type', 'summary')

        if not report_date:
            return JsonResponse({
                'success': False,
                'message': 'التاريخ مطلوب'
            }, status=400)

        from datetime import datetime
        report_date_obj = datetime.strptime(report_date, '%Y-%m-%d').date()

        # جلب بيانات الحسبور للتاريخ المحدد
        attendances = Attendance.objects.filter(
            session__session_date=report_date_obj
        ).select_related('student', 'session__group', 'session__group__teacher').order_by('-scan_time')

        if not attendances.exists():
            return JsonResponse({
                'success': False,
                'message': 'لا توجد بيانات لهذا التاريخ'
            })

        # إنشاء محتوى CSV
        import csv
        from io import StringIO

        output = StringIO()
        writer = csv.writer(output)

        if report_type == 'summary':
            # تقرير ملخص
            writer.writerow(['تقرير حضور مختصر', report_date])
            writer.writerow([])
            writer.writerow(['إجمالي الحضور', attendances.filter(status='present').count()])
            writer.writerow(['عدد المتأخرين', attendances.filter(status='late').count()])
            writer.writerow(['عدد الغياب', attendances.filter(status='absent').count()])

        elif report_type == 'detailed':
            # تقرير تفصيلي
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
                    att.scan_time.strftime('%I:%M %p')
                ])

        elif report_type == 'students':
            # قائمة الطلاب
            writer.writerow(['قائمة الطلاب المسجلين', report_date])
            writer.writerow([])
            writer.writerow(['اسم الطالب', 'كود الطالب', 'المجموعة', 'الحالة', 'وقت المسح'])

            for att in attendances:
                writer.writerow([
                    att.student.full_name,
                    att.student.student_code,
                    att.session.group.group_name,
                    att.get_status_display(),
                    att.scan_time.strftime('%I:%M %p')
                ])

        content = output.getvalue()

        return JsonResponse({
            'success': True,
            'content': content,
            'filename': f'attendance_report_{report_date}.csv'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'خطأ في التصدير: {str(e)}'
        }, status=500)


# ─────────────────────────────────────────────────────────────
# Scanner Quick-Action APIs  (Pay Now / Grace Period)
# ─────────────────────────────────────────────────────────────

@ajax_login_required
@require_http_methods(["POST"])
def scanner_pay_now(request):
    """
    Called from the scanner UI when the supervisor taps "ادفع الان".
    Marks the current-month payment as paid and activates the subscription.
    """
    import json as _json
    from apps.payments.models import Payment
    from apps.payments.api_views import _activate_student_for_payment

    try:
        body = _json.loads(request.body) if request.content_type == 'application/json' else request.POST
        payment_id = body.get('payment_id')
        student_id = body.get('student_id')

        if payment_id:
            payment = Payment.objects.get(pk=payment_id)
        elif student_id:
            # Find or create the current-month payment
            from apps.students.models import Student, StudentGroupEnrollment
            student = Student.objects.get(pk=student_id)
            current_month = timezone.localtime().date().replace(day=1)
            # Use the first active enrollment's group
            enr = StudentGroupEnrollment.objects.filter(
                student=student, is_active=True,
            ).select_related('group').first()
            if not enr:
                return JsonResponse({'success': False, 'message': 'لا يوجد تسجيل نشط'}, status=400)
            fee = student.get_monthly_fee_for_group(enr.group)
            payment, _ = Payment.objects.get_or_create(
                student=student, group=enr.group, month=current_month,
                defaults={'amount_due': fee, 'status': 'unpaid'},
            )
        else:
            return JsonResponse({'success': False, 'message': 'payment_id أو student_id مطلوب'}, status=400)

        # Mark as paid
        payment.amount_paid = payment.amount_due
        payment.status = 'paid'
        payment.payment_date = timezone.now()
        payment.save()

        # Activate subscription + enrollment
        _activate_student_for_payment(payment, user=request.user)

        return JsonResponse({
            'success': True,
            'message': f'تم تسديد الدفعة وتفعيل الاشتراك بنجاح',
        })
    except Payment.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'سجل الدفع غير موجود'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@ajax_login_required
@require_http_methods(["POST"])
def scanner_grace_period(request):
    """
    Called from the scanner UI when the supervisor taps "استثناء".
    Sets a grace_until date on the enrollment so the student can attend
    for X days WITHOUT changing their payment status.
    """
    import json as _json
    from datetime import timedelta
    from apps.students.models import Student, StudentGroupEnrollment

    try:
        body = _json.loads(request.body) if request.content_type == 'application/json' else request.POST
        student_id = body.get('student_id')
        group_id = body.get('group_id')
        days = int(body.get('days', 3))

        if not student_id:
            return JsonResponse({'success': False, 'message': 'student_id مطلوب'}, status=400)

        student = Student.objects.get(pk=student_id)

        # Extend subscription by X days so Step 1.5 passes
        student.activate_subscription(days=days)

        # Set grace_until on enrollments
        today = timezone.localtime().date()
        grace_date = today + timedelta(days=days)
        updated = StudentGroupEnrollment.objects.filter(
            student=student, is_active=True,
        ).update(grace_until=grace_date)

        # Also reactivate any inactive enrollments
        StudentGroupEnrollment.objects.filter(
            student=student, is_active=False,
        ).update(is_active=True, grace_until=grace_date)

        return JsonResponse({
            'success': True,
            'message': f'تم منح مهلة {days} أيام لـ {student.full_name} (حتى {grace_date})',
            'days': days,
            'grace_until': grace_date.isoformat(),
        })
    except Student.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'الطالب غير موجود'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@ajax_login_required
@require_http_methods(["POST"])
def grant_exception(request):
    """
    Grant an exception (payment or late-arrival) for a student.
    Called from the scanner UI by admin/supervisor.

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
    from apps.attendance.models import ActivityLog

    try:
        body = _json.loads(request.body) if request.content_type == 'application/json' else request.POST
        student_id = body.get('student_id')
        group_id = body.get('group_id')
        session_id = body.get('session_id')
        exception_type = body.get('exception_type', 'payment')
        reason_type = body.get('reason_type', 'other')
        custom_reason = body.get('custom_reason', '')

        if not student_id:
            return JsonResponse({'success': False, 'message': 'student_id مطلوب'}, status=400)

        student = Student.objects.get(pk=student_id)
        group = None
        if group_id:
            group = Group.objects.get(pk=group_id)

        session = None
        if session_id:
            session = SessionModel.objects.filter(pk=session_id).first()

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
            from .services import AttendanceService
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
            pass  # Celery may not be available; notification is non-critical

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
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


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


@ajax_login_required
@require_http_methods(["POST"])
def revoke_exception(request, exception_id):
    """
    Revoke (deactivate) an exception. The exception remains in the log
    but is marked inactive so it won't be considered for future scans.
    """
    from .models import ExceptionRecord
    from apps.attendance.models import ActivityLog

    try:
        exception = ExceptionRecord.objects.get(pk=exception_id)
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
