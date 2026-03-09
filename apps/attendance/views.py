from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.utils import timezone
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


@login_required
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


@login_required
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


@login_required
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


@login_required
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
