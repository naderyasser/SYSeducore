from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from apps.accounts.decorators import ajax_login_required
from apps.attendance.models import ActivityLog
from .models import Payment


def _activate_student_for_payment(payment, user=None):
    """
    After a payment is marked as paid, ensure the student can immediately
    pass the attendance scanner by:
      1. Activating the student's subscription (30-day expiry).
      2. Ensuring the StudentGroupEnrollment for this group is active.

    This bridges the gap between the payments app and the attendance
    scanner so that process_scan() finds an active enrollment and a
    valid subscription right after payment.
    """
    from apps.students.models import StudentGroupEnrollment

    student = payment.student

    # 1. Activate subscription (30 days from today)
    student.activate_subscription(days=30)

    # 2. Ensure enrollment is active for the payment's group
    enrollment, created = StudentGroupEnrollment.objects.get_or_create(
        student=student,
        group=payment.group,
        defaults={'is_active': True},
    )
    if not created and not enrollment.is_active:
        enrollment.is_active = True
        enrollment.save(update_fields=['is_active'])

    # 3. Make sure the student record itself is active
    if not student.is_active:
        student.is_active = True
        student.save(update_fields=['is_active'])

    # Log the activation
    if user:
        ActivityLog.log(
            user=user,
            action='payment_record',
            description=(
                f'تسديد + تفعيل: {student.full_name} — '
                f'{payment.group.group_name} — '
                f'الاشتراك حتى {student.subscription_expiry_date}'
            ),
            target_model='Payment',
            target_id=payment.pk,
        )


@ajax_login_required
@require_http_methods(["POST"])
def record_payment(request, payment_id):
    """
    API endpoint لتسجيل دفع
    When the payment is fully paid, also activate the student's
    subscription and enrollment so the scanner recognises them.
    """
    try:
        payment = Payment.objects.get(pk=payment_id)
        amount = Decimal(request.POST.get('amount', '0'))
        
        payment.amount_paid += amount
        payment.payment_date = timezone.now()
        
        # Update status based on amount
        if payment.amount_paid >= payment.amount_due:
            payment.status = 'paid'
        elif payment.amount_paid > 0:
            payment.status = 'partial'
        
        payment.save()

        # Auto-activate when fully paid
        if payment.status == 'paid':
            _activate_student_for_payment(payment, user=request.user)
        
        return JsonResponse({
            'success': True,
            'new_amount_paid': float(payment.amount_paid),
            'status': payment.status,
            'status_display': payment.get_status_display()
        })
    except Payment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Payment not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@ajax_login_required
@require_http_methods(["POST"])
def mark_as_paid(request, payment_id):
    """
    تسديد الدفعة بالكامل + تفعيل الاشتراك والتسجيل
    """
    try:
        payment = Payment.objects.get(pk=payment_id)
        
        payment.amount_paid = payment.amount_due
        payment.status = 'paid'
        payment.payment_date = timezone.now()
        payment.save()

        # Activate subscription + enrollment so scanner works immediately
        _activate_student_for_payment(payment, user=request.user)
        
        return JsonResponse({
            'success': True,
            'message': 'تم تسديد الدفعة وتفعيل الاشتراك بنجاح',
            'payment': {
                'payment_id': payment.payment_id,
                'amount_paid': float(payment.amount_paid),
                'status': payment.status
            }
        })
    except Payment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'الدفعة غير موجودة'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)
