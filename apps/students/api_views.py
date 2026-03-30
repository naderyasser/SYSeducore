"""
API Views for Students App
Handles barcode generation, WhatsApp sharing, group enrollment, and ID card generation
"""
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count, Q
from django.utils import timezone
from django.conf import settings
from datetime import datetime, timedelta
import base64
import io
import os
import requests
import qrcode
from PIL import Image

from .models import Student, StudentGroupEnrollment
from apps.teachers.models import Group
from apps.attendance.models import Attendance
from apps.notifications.services import WhatsAppService


def generate_qr_image(code):
    """Helper function to generate QR code image"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=3,
    )
    qr.add_data(code)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert('RGB')


@login_required
@require_http_methods(["GET"])
def student_barcode(request, student_id):
    """
    Generate QR code for student as base64 image
    """
    student = get_object_or_404(Student, pk=student_id)

    try:
        img = generate_qr_image(student.student_code)
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()

        return JsonResponse({
            'success': True,
            'barcode': f'data:image/png;base64,{img_str}',
            'student_code': student.student_code,
            'student_name': student.full_name
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Failed to generate QR code: {str(e)}'
        })


@login_required
@require_http_methods(["POST"])
def send_barcode_whatsapp(request, student_id):
    """
    Send barcode image to student's parent via WhatsApp.
    Uses UltraMsg API to send actual image.
    """
    student = get_object_or_404(Student, pk=student_id)

    try:
        # Generate QR code image
        img = generate_qr_image(student.student_code)
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        # Get WhatsApp service
        wa_service = WhatsAppService()

        # Format phone number
        phone = wa_service._format_phone_number(student.parent_phone)

        # Prepare message
        message = f"""*بطاقة الطالب - {student.full_name}*

كود الطالب: *{student.student_code}*

يرجى الاحتفاظ بهذا الكود لتسجيل الحضور في المركز.

_نظام بداية التعليمي_"""

        # Try to send image via UltraMsg
        instance_id = getattr(settings, 'ULTRAMSG_INSTANCE_ID', '')
        token = getattr(settings, 'ULTRAMSG_TOKEN', '')

        if instance_id and token:
            # Save image temporarily
            temp_path = os.path.join(settings.MEDIA_ROOT, 'temp', f'barcode_{student.student_code}.png')
            os.makedirs(os.path.dirname(temp_path), exist_ok=True)
            img.save(temp_path)

            # Send via UltraMsg image API
            url = f'https://api.ultramsg.com/{instance_id}/messages/image'

            with open(temp_path, 'rb') as img_file:
                img_base64 = base64.b64encode(img_file.read()).decode()

            payload = {
                'token': token,
                'to': phone,
                'image': img_base64,
                'caption': message
            }

            response = requests.post(url, json=payload, timeout=30)
            result = response.json()

            # Clean up temp file
            try:
                os.remove(temp_path)
            except:
                pass

            if result.get('status') == 'success' or result.get('sent') == 'true':
                return JsonResponse({
                    'success': True,
                    'message': 'تم إرسال الباركود بنجاح عبر الواتساب'
                })
            else:
                # Fallback: send link only
                fallback_result = wa_service.send_message(
                    phone,
                    f"{message}\n\nملاحظة: فشل إرسال الصورة، يرجى التواصل مع الإدارة."
                )
                return JsonResponse({
                    'success': fallback_result.get('success', False),
                    'message': fallback_result.get('message', 'تم إرسال الرسالة بدون صورة')
                })
        else:
            return JsonResponse({
                'success': False,
                'message': 'إعدادات الواتساب غير مكتملة'
            })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ: {str(e)}'
        })


@login_required
@require_http_methods(["POST"])
def add_to_group(request):
    """
    Add student to a group with financial status
    """
    student_id = request.POST.get('student_id')
    group_id = request.POST.get('group_id')
    financial_status = request.POST.get('financial_status', 'normal')
    custom_fee = request.POST.get('custom_fee')

    if not student_id or not group_id:
        return JsonResponse({
            'success': False,
            'message': 'بيانات ناقصة'
        })

    student = get_object_or_404(Student, pk=student_id)
    group = get_object_or_404(Group, pk=group_id)

    # Check if already enrolled
    enrollment = StudentGroupEnrollment.objects.filter(
        student=student,
        group=group
    ).first()

    if enrollment:
        # Update existing enrollment
        enrollment.financial_status = financial_status
        if financial_status == 'symbolic' and custom_fee:
            enrollment.custom_fee = custom_fee
        else:
            enrollment.custom_fee = None
        enrollment.is_active = True
        enrollment.save()
        message = 'تم تحديث تسجيل الطالب في المجموعة'
    else:
        # Create new enrollment
        enrollment_data = {
            'student': student,
            'group': group,
            'financial_status': financial_status,
            'is_active': True
        }
        if financial_status == 'symbolic' and custom_fee:
            enrollment_data['custom_fee'] = custom_fee

        enrollment = StudentGroupEnrollment.objects.create(**enrollment_data)
        message = 'تم إضافة الطالب للمجموعة بنجاح'

    return JsonResponse({
        'success': True,
        'message': message,
        'enrollment': {
            'id': enrollment.id,
            'group_name': group.group_name,
            'teacher_name': group.teacher.full_name if group.teacher else '-',
            'financial_status': enrollment.get_financial_status_display()
        }
    })


@login_required
@require_http_methods(["POST"])
def remove_from_group(request):
    """
    Remove student from a group (soft delete by setting is_active=False)
    """
    enrollment_id = request.POST.get('enrollment_id')

    if not enrollment_id:
        return JsonResponse({
            'success': False,
            'message': 'بيانات ناقصة'
        })

    enrollment = get_object_or_404(StudentGroupEnrollment, pk=enrollment_id)
    enrollment.is_active = False
    enrollment.save()

    return JsonResponse({
        'success': True,
        'message': 'تم إزالة الطالب من المجموعة'
    })


@login_required
@require_http_methods(["GET"])
def student_groups(request, student_id):
    """
    Get all groups for a student with enrollment details
    """
    student = get_object_or_404(Student, pk=student_id)

    enrollments = StudentGroupEnrollment.objects.filter(
        student=student,
        is_active=True
    ).select_related('group', 'group__teacher')

    groups_data = []
    for enrollment in enrollments:
        group = enrollment.group
        groups_data.append({
            'enrollment_id': enrollment.id,
            'group_id': group.group_id,
            'group_name': group.group_name,
            'teacher_name': group.teacher.full_name if group.teacher else '-',
            'schedule_day': group.get_schedule_day_display(),
            'schedule_time': group.schedule_time.strftime('%H:%M') if group.schedule_time else '--:--',
            'room_name': group.room.name if group.room else '-',
            'standard_fee': str(group.standard_fee),
            'financial_status': enrollment.financial_status,
            'financial_status_display': enrollment.get_financial_status_display(),
            'custom_fee': str(enrollment.custom_fee) if enrollment.custom_fee else None
        })

    return JsonResponse({
        'success': True,
        'groups': groups_data
    })


@login_required
@require_http_methods(["GET"])
def available_groups(request, student_id):
    """
    Get groups that the student is not enrolled in
    Filtered by gender compatibility and education stage/year
    المجموعات المتاحة حسب جنس الطالب ومرحلته الدراسية
    """
    student = get_object_or_404(Student, pk=student_id)

    # Get groups student is already enrolled in
    enrolled_group_ids = StudentGroupEnrollment.objects.filter(
        student=student,
        is_active=True
    ).values_list('group_id', flat=True)

    # Get available groups
    available = Group.objects.filter(
        is_active=True
    ).exclude(
        group_id__in=enrolled_group_ids
    ).select_related('teacher', 'room')

    # Filter by gender compatibility
    if student.gender == 'male':
        available = available.exclude(gender_type='female')
    elif student.gender == 'female':
        available = available.exclude(gender_type='male')

    # Filter by education stage if set
    if student.education_stage:
        available = available.filter(
            Q(education_stage=student.education_stage) | Q(education_stage='')
        )
    if student.education_year:
        available = available.filter(
            Q(education_year=student.education_year) | Q(education_year='')
        )

    groups_data = []
    for group in available:
        # Check if group has capacity
        enrolled_count = StudentGroupEnrollment.objects.filter(
            group=group,
            is_active=True
        ).count()

        groups_data.append({
            'group_id': group.group_id,
            'group_name': group.group_name,
            'teacher_name': group.teacher.full_name if group.teacher else '-',
            'schedule_day': group.get_schedule_day_display(),
            'schedule_time': group.schedule_time.strftime('%H:%M') if group.schedule_time else '--:--',
            'time_end': group.get_end_time().strftime('%H:%M'),
            'duration': group.get_duration_display(),
            'room_name': group.room.name if group.room else '-',
            'standard_fee': str(group.standard_fee),
            'gender_type': group.get_gender_type_display(),
            'education_stage': group.get_education_stage_display() if group.education_stage else '-',
            'education_year': group.get_education_year_display() if group.education_year else '-',
            'capacity': group.room.capacity if group.room else 0,
            'enrolled': enrolled_count,
            'available': (group.room.capacity - enrolled_count) if group.room else 0
        })

    return JsonResponse({
        'success': True,
        'groups': groups_data
    })


@login_required
@require_http_methods(["GET"])
def student_id_card_data(request, student_id):
    """
    Generate ID card data for printing
    Returns student info with barcode and formatted dates
    الوجه: بيانات الطالب + QR Code
    الظهر: طباعة صور المدرسين المشترك معهم الطالب (ديناميكي)
    """
    student = get_object_or_404(Student, pk=student_id)

    # Get student's active groups
    enrollments = StudentGroupEnrollment.objects.filter(
        student=student,
        is_active=True
    ).select_related('group', 'group__teacher', 'group__room')[:3]  # Max 3 groups on card

    groups_info = []
    teacher_photos = []  # For card back
    for enrollment in enrollments:
        group = enrollment.group
        groups_info.append({
            'name': group.group_name,
            'teacher': group.teacher.full_name if group.teacher else '-',
            'schedule': f"{group.get_schedule_day_display()} {group.schedule_time.strftime('%H:%M') if group.schedule_time else ''} - {group.get_end_time().strftime('%H:%M')}",
            'room': group.room.name if group.room else '-',
            'subjects': group.teacher.get_subjects_display() if group.teacher else '-',
        })

        # Collect teacher photos for card back
        if group.teacher and group.teacher.photo:
            teacher_photos.append({
                'name': group.teacher.full_name,
                'photo_url': group.teacher.photo.url,
                'subjects': group.teacher.get_subjects_display(),
            })

    # Get enrollment date
    enrollment_date = student.created_at.strftime('%Y-%m-%d') if student.created_at else '-'

    # Get recent attendance (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_attendance = Attendance.objects.filter(
        student__student_id=student_id,
        scan_time__gte=thirty_days_ago
    ).count()

    # Generate barcode base64
    barcode_base64 = student.get_barcode_base64()

    return JsonResponse({
        'success': True,
        'student': {
            'id': student.student_id,
            'code': student.student_code,
            'name': student.full_name,
            'gender': student.get_gender_display(),
            'education': student.get_education_display_full(),
            'student_phone': student.student_phone,
            'parent_phone': student.parent_phone,
            'enrollment_date': enrollment_date,
            'groups': groups_info,
            'recent_attendance': recent_attendance,
            'barcode_base64': barcode_base64,
            'teacher_photos': teacher_photos,  # For card back
        }
    })


@login_required
@require_http_methods(["GET"])
def whatsapp_barcode(request, student_id):
    """
    Generate WhatsApp share link with barcode image
    Returns the barcode image and WhatsApp link
    """
    student = get_object_or_404(Student, pk=student_id)

    # Generate QR code image
    img = generate_qr_image(student.student_code)
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode()

    # Create WhatsApp message
    wa_service = WhatsAppService()
    phone_number = wa_service._format_phone_number(student.parent_phone)

    message = f"مرحباً {student.full_name}،\n\nكود الطالب الخاص بك هو: {student.student_code}\n\nيرجى الاحتفاظ بهذا الكود لتسجيل الحضور."

    whatsapp_link = f"https://wa.me/{phone_number}?text={requests.utils.quote(message)}"

    return JsonResponse({
        'success': True,
        'barcode': f'data:image/png;base64,{img_str}',
        'whatsapp_link': whatsapp_link,
        'phone': phone_number,
        'message': message
    })


@login_required
@require_http_methods(["GET"])
def students_list_api(request):
    """
    API endpoint for students list with filtering and pagination
    Returns detailed student data with barcodes
    """
    search = request.GET.get('search', '')
    group_filter = request.GET.get('group', '')
    status_filter = request.GET.get('status', '')

    students = Student.objects.all().annotate(
        groups_count=Count('groups', filter=Q(group_enrollments__is_active=True))
    )

    # Apply filters
    if search:
        students = students.filter(
            Q(full_name__icontains=search) |
            Q(student_code__icontains=search) |
            Q(parent_phone__icontains=search)
        )

    if group_filter:
        students = students.filter(groups__group_id=group_filter)

    if status_filter == 'with_groups':
        students = students.filter(groups_count__gt=0)
    elif status_filter == 'no_groups':
        students = students.filter(groups_count=0)
    elif status_filter == 'active':
        students = students.filter(is_active=True)
    elif status_filter == 'inactive':
        students = students.filter(is_active=False)

    # Order by most recent
    students = students.order_by('-created_at')

    students_data = []
    for student in students[:100]:  # Limit to 100 for performance
        # Get barcode base64
        try:
            barcode = student.get_barcode_base64()
        except:
            barcode = None

        students_data.append({
            'id': student.student_id,
            'code': student.student_code,
            'name': student.full_name,
            'phone': student.parent_phone,
            'is_active': student.is_active,
            'groups_count': student.groups_count,
            'created_at': student.created_at.strftime('%Y-%m-%d') if student.created_at else None,
            'barcode_base64': barcode
        })

    return JsonResponse({
        'success': True,
        'students': students_data
    })


@login_required
@require_http_methods(["GET"])
def student_statistics(request):
    """
    Get overall student statistics
    """
    total_students = Student.objects.filter(is_active=True).count()

    students_with_groups = Student.objects.filter(
        is_active=True,
        groups__is_active=True
    ).distinct().count()

    students_without_groups = total_students - students_with_groups

    # Get recent registrations (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_registrations = Student.objects.filter(
        is_active=True,
        created_at__gte=thirty_days_ago
    ).count()

    # Get total groups count
    total_groups = Group.objects.filter(is_active=True).count()

    return JsonResponse({
        'success': True,
        'statistics': {
            'total': total_students,
            'with_groups': students_with_groups,
            'without_groups': students_without_groups,
            'recent_registrations': recent_registrations,
            'total_groups': total_groups
        }
    })


@login_required
@require_http_methods(["POST"])
def bulk_action(request):
    """
    Perform bulk actions on students
    Actions: delete, activate, deactivate
    """
    action = request.POST.get('action')
    student_ids = request.POST.getlist('student_ids[]')

    if not action or not student_ids:
        return JsonResponse({
            'success': False,
            'message': 'بيانات غير مكتملة'
        })

    students = Student.objects.filter(student_id__in=student_ids)
    count = students.count()

    if action == 'delete':
        students.update(is_active=False)
        message = f'تم حذف {count} طالب بنجاح'
    elif action == 'activate':
        students.update(is_active=True)
        message = f'تم تفعيل {count} طالب بنجاح'
    elif action == 'deactivate':
        students.update(is_active=False)
        message = f'تم إلغاء تفعيل {count} طالب بنجاح'
    else:
        return JsonResponse({
            'success': False,
            'message': 'إجراء غير معروف'
        })

    return JsonResponse({
        'success': True,
        'message': message,
        'affected': count
    })


@login_required
@require_http_methods(["POST"])
def activate_subscription(request, student_id):
    """
    تفعيل اشتراك الطالب لمدة 30 يوم
    """
    try:
        student = get_object_or_404(Student, pk=student_id)
        days = int(request.POST.get('days', 30))
        
        expiry_date = student.activate_subscription(days=days)
        subscription_status = student.get_subscription_status()
        
        return JsonResponse({
            'success': True,
            'message': f'تم تفعيل اشتراك {student.full_name} لمدة {days} يوم',
            'student': {
                'student_id': student.student_id,
                'full_name': student.full_name,
                'last_payment_date': student.last_payment_date.isoformat() if student.last_payment_date else None,
                'subscription_expiry_date': student.subscription_expiry_date.isoformat() if student.subscription_expiry_date else None,
            },
            'subscription_status': subscription_status
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'خطأ: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["GET"])
def subscription_status(request, student_id):
    """
    الحصول على حالة اشتراك الطالب
    """
    try:
        student = get_object_or_404(Student, pk=student_id)
        subscription_status = student.get_subscription_status()
        
        return JsonResponse({
            'success': True,
            'student': {
                'student_id': student.student_id,
                'full_name': student.full_name,
                'last_payment_date': student.last_payment_date.isoformat() if student.last_payment_date else None,
                'subscription_expiry_date': student.subscription_expiry_date.isoformat() if student.subscription_expiry_date else None,
                'is_active': student.is_subscription_active(),
            },
            'subscription_status': subscription_status
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'خطأ: {str(e)}'
        }, status=500)
