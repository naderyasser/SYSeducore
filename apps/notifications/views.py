from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import json
from .services import WhatsAppService
from apps.teachers.models import Group


@login_required
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
