"""
API Views for Students App
Handles barcode generation, WhatsApp sharing, group enrollment, and ID card generation
"""
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
import base64
import io
import logging
import requests
import qrcode

from .models import Student, StudentGroupEnrollment
from .utils import (
    enrollment_compatibility_errors,
    normalize_financial_status,
    parse_money,
    valid_financial_statuses,
)
from apps.accounts.decorators import ajax_login_required, ajax_supervisor_required
from apps.teachers.models import Group
from apps.attendance.models import Attendance, ActivityLog
from apps.notifications.services import WhatsAppService

logger = logging.getLogger(__name__)

#: Generic client-facing error message. Details go to the log, never to the
#: browser — raw exception text leaks model names, SQL fragments and paths.
GENERIC_ERROR_MESSAGE = 'حدث خطأ غير متوقع، يرجى المحاولة مرة أخرى أو التواصل مع الدعم'

#: Default / maximum page size for the students list API.
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


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


@ajax_login_required
@require_http_methods(["GET"])
def student_barcode(request, student_id):
    """
    Generate Code128 barcode for student as base64 image
    """
    student = get_object_or_404(Student, pk=student_id)

    try:
        img_str = student.get_barcode_base64()
        if not img_str:
            raise ValueError('Failed to generate barcode')

        return JsonResponse({
            'success': True,
            'barcode': f'data:image/png;base64,{img_str}',
            'student_code': student.student_code,
            'student_name': student.full_name
        })
    except Exception:
        logger.exception('Barcode generation failed for student %s', student.pk)
        return JsonResponse({
            'success': False,
            'message': 'تعذر إنشاء الباركود لهذا الطالب'
        }, status=500)


@ajax_login_required
@require_http_methods(["POST"])
def send_barcode_whatsapp(request, student_id):
    """
    Send the student's code to their parent via WhatsApp.

    Rewritten to use the live ``WhatsAppService`` (WASender) that the rest of
    the system uses. The previous implementation called the decommissioned
    UltraMsg *image* API behind ``ULTRAMSG_*`` settings that are empty by
    default, so the button always answered "إعدادات الواتساب غير مكتملة"; it
    also wrote a temp PNG into MEDIA_ROOT that leaked whenever the request
    raised, and blocked the worker for up to 30s. WASender has no image
    endpoint here, so a text message carrying the code is sent instead — the
    printable card/sticker endpoints cover the image case.
    """
    student = get_object_or_404(Student, pk=student_id)

    if not student.parent_phone:
        return JsonResponse({
            'success': False,
            'message': 'لا يوجد رقم هاتف لولي أمر هذا الطالب'
        }, status=400)

    message = f"""*بطاقة الطالب - {student.full_name}*

كود الطالب: *{student.student_code}*

يرجى الاحتفاظ بهذا الكود لتسجيل الحضور في المركز.

_نظام بداية التعليمي_"""

    try:
        wa_service = WhatsAppService()
        result = wa_service.send_message(student.parent_phone, message)
    except Exception:
        logger.exception('WhatsApp send failed for student %s', student.pk)
        return JsonResponse({
            'success': False,
            'message': 'تعذر إرسال الرسالة عبر الواتساب حالياً'
        }, status=502)

    if result.get('success'):
        return JsonResponse({
            'success': True,
            'message': 'تم إرسال كود الطالب بنجاح عبر الواتساب'
        })

    logger.warning(
        'WhatsApp send rejected for student %s: %s',
        student.pk, result.get('error'),
    )
    return JsonResponse({
        'success': False,
        'message': 'تعذر إرسال الرسالة عبر الواتساب، يرجى مراجعة إعدادات الواتساب'
    })


@ajax_supervisor_required
@require_http_methods(["POST"])
def add_to_group(request):
    """
    Add student to a group with financial status.

    Enrolling a student and setting their fee terms is a desk operation, so it
    requires supervisor+ — this endpoint used to accept any authenticated user
    and took ``financial_status`` straight from POST, which let anyone mark any
    student (or themselves) as 'exempt', or store an arbitrary 15-char string
    that no ``get_financial_status_display()`` could ever render.
    """
    student_id = request.POST.get('student_id')
    group_id = request.POST.get('group_id')
    raw_status = request.POST.get('financial_status', 'normal')
    raw_custom_fee = request.POST.get('custom_fee')

    if not student_id or not group_id:
        return JsonResponse({
            'success': False,
            'message': 'بيانات ناقصة'
        }, status=400)

    try:
        student_id = int(student_id)
        group_id = int(group_id)
    except (TypeError, ValueError):
        return JsonResponse({
            'success': False,
            'message': 'بيانات غير صحيحة'
        }, status=400)

    if raw_status and raw_status not in valid_financial_statuses():
        return JsonResponse({
            'success': False,
            'message': 'الحالة المالية غير صحيحة'
        }, status=400)
    financial_status = normalize_financial_status(raw_status)

    custom_fee = None
    if financial_status == 'symbolic':
        custom_fee = parse_money(raw_custom_fee)
        if custom_fee is None:
            return JsonResponse({
                'success': False,
                'message': 'يجب تحديد مبلغ صحيح (رقم موجب) للحالة المالية الرمزية'
            }, status=400)

    student = get_object_or_404(Student, pk=student_id)
    group = get_object_or_404(Group, pk=group_id)

    # Same gender / education-stage rules the enrollment form enforces
    compatibility_errors = enrollment_compatibility_errors(student, group)
    if compatibility_errors:
        return JsonResponse({
            'success': False,
            'message': compatibility_errors[0],
            'errors': compatibility_errors,
        }, status=400)

    with transaction.atomic():
        # Check if already enrolled (including a previously removed enrollment)
        enrollment = StudentGroupEnrollment.objects.select_for_update().filter(
            student=student,
            group=group
        ).first()

        if enrollment:
            enrollment.financial_status = financial_status
            enrollment.custom_fee = custom_fee
            enrollment.is_active = True
            enrollment.save(update_fields=['financial_status', 'custom_fee', 'is_active'])
            message = 'تم تحديث تسجيل الطالب في المجموعة'
            log_description = (
                f'تحديث تسجيل الطالب {student.full_name} في المجموعة {group.group_name} '
                f'(الحالة المالية: {enrollment.get_financial_status_display()})'
            )
        else:
            enrollment = StudentGroupEnrollment.objects.create(
                student=student,
                group=group,
                financial_status=financial_status,
                custom_fee=custom_fee,
                is_active=True,
            )
            message = 'تم إضافة الطالب للمجموعة بنجاح'
            log_description = (
                f'تسجيل الطالب {student.full_name} في المجموعة {group.group_name} '
                f'(الحالة المالية: {enrollment.get_financial_status_display()})'
            )

        ActivityLog.log(
            user=request.user, action='enrollment_create',
            description=log_description,
            target_model='StudentGroupEnrollment', target_id=enrollment.pk,
            request=request,
        )

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


@ajax_supervisor_required
@require_http_methods(["POST"])
def remove_from_group(request):
    """
    Remove student from a group (soft delete by setting is_active=False).
    Supervisor+ only: un-enrolling changes what the scanner lets a student do.
    """
    enrollment_id = request.POST.get('enrollment_id')

    if not enrollment_id:
        return JsonResponse({
            'success': False,
            'message': 'بيانات ناقصة'
        }, status=400)

    try:
        enrollment_id = int(enrollment_id)
    except (TypeError, ValueError):
        return JsonResponse({
            'success': False,
            'message': 'بيانات غير صحيحة'
        }, status=400)

    enrollment = get_object_or_404(
        StudentGroupEnrollment.objects.select_related('student', 'group'),
        pk=enrollment_id,
    )
    enrollment.is_active = False
    enrollment.save(update_fields=['is_active'])

    ActivityLog.log(
        user=request.user, action='enrollment_remove',
        description=(
            f'إزالة الطالب {enrollment.student.full_name} '
            f'من المجموعة {enrollment.group.group_name}'
        ),
        target_model='StudentGroupEnrollment', target_id=enrollment.pk,
        request=request,
    )

    return JsonResponse({
        'success': True,
        'message': 'تم إزالة الطالب من المجموعة'
    })


@ajax_login_required
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


@ajax_login_required
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


@ajax_login_required
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


@ajax_login_required
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


@ajax_login_required
@require_http_methods(["GET"])
def students_list_api(request):
    """
    API endpoint for students list with filtering and pagination.

    Barcodes are **not** included: rendering a 300-dpi Code128 PNG per student
    (up to 100 per request, synchronously) is what made this endpoint slow.
    Use ``students:api_barcode`` for the one student that actually needs one.
    """
    search = request.GET.get('search', '')
    group_filter = request.GET.get('group', '')
    status_filter = request.GET.get('status', '')

    # Count the enrollment rows, not the M2M join — see students/views.py
    students = Student.objects.all().annotate(
        groups_count=Count(
            'group_enrollments',
            filter=Q(group_enrollments__is_active=True),
            distinct=True,
        )
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

    # Order by most recent (stable secondary key so pages never overlap)
    students = students.order_by('-created_at', '-student_id')

    # Real pagination — the docstring used to promise it while the code just
    # truncated at 100 rows.
    try:
        page_size = int(request.GET.get('page_size', DEFAULT_PAGE_SIZE))
    except (TypeError, ValueError):
        page_size = DEFAULT_PAGE_SIZE
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))

    paginator = Paginator(students, page_size)
    page_obj = paginator.get_page(request.GET.get('page'))

    students_data = [{
        'id': student.student_id,
        'code': student.student_code,
        'name': student.full_name,
        'phone': student.parent_phone,
        'is_active': student.is_active,
        'groups_count': student.groups_count,
        'created_at': student.created_at.strftime('%Y-%m-%d') if student.created_at else None,
    } for student in page_obj.object_list]

    return JsonResponse({
        'success': True,
        'students': students_data,
        'pagination': {
            'page': page_obj.number,
            'page_size': page_size,
            'total_pages': paginator.num_pages,
            'total': paginator.count,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        },
    })


@ajax_login_required
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


@ajax_supervisor_required
@require_http_methods(["POST"])
def bulk_action(request):
    """
    Perform bulk actions on students.
    Actions: delete (soft delete → recycle bin), activate, deactivate.

    Supervisor+ only: mass-mutating student state is a desk operation.
    """
    action = request.POST.get('action')
    student_ids = request.POST.getlist('student_ids[]') or request.POST.getlist('student_ids')

    if not action or not student_ids:
        return JsonResponse({
            'success': False,
            'message': 'بيانات غير مكتملة'
        }, status=400)

    if action not in ('delete', 'activate', 'deactivate'):
        return JsonResponse({
            'success': False,
            'message': 'إجراء غير معروف'
        }, status=400)

    student_ids = [sid for sid in student_ids if str(sid).isdigit()]
    if not student_ids:
        return JsonResponse({
            'success': False,
            'message': 'بيانات غير مكتملة'
        }, status=400)

    with transaction.atomic():
        students = list(
            Student.objects.select_for_update().filter(student_id__in=student_ids)
        )
        count = len(students)
        pks = [s.student_id for s in students]

        if action == 'delete':
            # This used to only flip is_active=False while reporting
            # "تم حذف N طالب" — the students never reached the recycle bin and
            # kept showing up in every list. Do a real soft delete, and stop
            # their enrollments so the absence/notification crons let go of them.
            now = timezone.now()
            Student.objects.filter(student_id__in=pks).update(
                deleted_at=now, deleted_by=request.user, is_active=False,
            )
            StudentGroupEnrollment.objects.filter(
                student_id__in=pks, is_active=True,
            ).update(is_active=False)
            message = f'تم نقل {count} طالب إلى سلة المهملات'
            log_action = 'student_delete'
            log_description = f'حذف جماعي (سلة المهملات) لعدد {count} طالب'
        elif action == 'activate':
            Student.objects.filter(student_id__in=pks).update(is_active=True)
            message = f'تم تفعيل {count} طالب بنجاح'
            log_action = 'student_toggle'
            log_description = f'تفعيل جماعي لعدد {count} طالب'
        else:  # deactivate
            Student.objects.filter(student_id__in=pks).update(is_active=False)
            message = f'تم إلغاء تفعيل {count} طالب بنجاح'
            log_action = 'student_toggle'
            log_description = f'إلغاء تفعيل جماعي لعدد {count} طالب'

        if count:
            ActivityLog.log(
                user=request.user, action=log_action, description=log_description,
                target_model='Student', target_id=None, request=request,
            )

    return JsonResponse({
        'success': True,
        'message': message,
        'affected': count
    })


@ajax_supervisor_required
@require_http_methods(["POST"])
def activate_subscription(request, student_id):
    """
    تفعيل اشتراك الطالب لمدة 30 يوم

    This moves money: it marks the current month's Payment rows as fully paid.
    It is therefore supervisor+ (it used to be open to any authenticated
    account, teachers included), runs in a single transaction, and writes an
    ActivityLog entry so "who marked this paid?" has an answer.

    It no longer re-activates *every* previously removed enrollment — a
    deliberate un-enrollment is not something a payment should undo. Only
    enrollments that are already active are billed and paid.
    """
    # Use all_objects to include soft-deleted students (payments may still reference them)
    try:
        student = Student.all_objects.get(pk=student_id)
    except Student.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'الطالب غير موجود'}, status=404)

    try:
        days = int(request.POST.get('days', 30))
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'message': 'عدد الأيام غير صحيح'}, status=400)
    if days <= 0 or days > 366:
        return JsonResponse({
            'success': False,
            'message': 'عدد الأيام يجب أن يكون بين 1 و 366'
        }, status=400)

    try:
        from apps.payments.models import Payment

        with transaction.atomic():
            student.activate_subscription(days=days)

            # ── Ensure current-month Payment rows exist and are marked 'paid' ──
            # Activating a subscription means the student has paid, so every
            # active enrollment must have a Payment(status='paid') for the
            # current month — otherwise check_financial_status() still rejects.
            current_month = timezone.localdate().replace(day=1)
            payments_updated = 0
            for enr in StudentGroupEnrollment.objects.filter(
                student=student, is_active=True,
            ).select_related('group'):
                fee = student.get_monthly_fee_for_group(enr.group)
                payment, created = Payment.objects.get_or_create(
                    student=student,
                    group=enr.group,
                    month=current_month,
                    defaults={
                        'amount_due': fee,
                        'amount_paid': fee,
                        'status': 'paid',
                        'payment_date': timezone.now(),
                    },
                )
                if created:
                    payments_updated += 1
                elif payment.status != 'paid':
                    payment.amount_paid = payment.amount_due
                    payment.status = 'paid'
                    payment.payment_date = timezone.now()
                    payment.save(update_fields=['amount_paid', 'status', 'payment_date'])
                    payments_updated += 1

            ActivityLog.log(
                user=request.user,
                action='payment_record',
                description=(
                    f'تفعيل اشتراك الطالب {student.full_name} '
                    f'(كود: {student.student_code}) لمدة {days} يوم '
                    f'وتسجيل {payments_updated} دفعة كمدفوعة'
                ),
                target_model='Student',
                target_id=student.student_id,
                request=request,
            )
    except Exception:
        logger.exception('activate_subscription failed for student %s', student_id)
        return JsonResponse({
            'success': False,
            'message': GENERIC_ERROR_MESSAGE
        }, status=500)

    subscription_status = student.get_subscription_status()

    return JsonResponse({
        'success': True,
        'message': f'تم تفعيل اشتراك {student.full_name} لمدة {days} يوم + تحديث {payments_updated} سجل دفع',
        'student': {
            'student_id': student.student_id,
            'full_name': student.full_name,
            'last_payment_date': student.last_payment_date.isoformat() if student.last_payment_date else None,
            'subscription_expiry_date': student.subscription_expiry_date.isoformat() if student.subscription_expiry_date else None,
        },
        # Kept for API compatibility; blanket re-activation was removed.
        'reactivated_enrollments': 0,
        'payments_updated': payments_updated,
        'subscription_status': subscription_status
    })


@ajax_login_required
@require_http_methods(["GET"])
def subscription_status(request, student_id):
    """
    الحصول على حالة اشتراك الطالب
    """
    try:
        try:
            student = Student.all_objects.get(pk=student_id)
        except Student.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'الطالب غير موجود'}, status=404)
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
    except Exception:
        logger.exception('subscription_status failed for student %s', student_id)
        return JsonResponse({
            'success': False,
            'message': GENERIC_ERROR_MESSAGE
        }, status=500)
