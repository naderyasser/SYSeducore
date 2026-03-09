from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
import json
from .models import Payment


@login_required
@require_http_methods(["POST"])
def record_payment(request, payment_id):
    """
    API endpoint لتسجيل دفع
    """
    try:
        payment = Payment.objects.get(pk=payment_id)
        amount = float(request.POST.get('amount', 0))
        
        payment.amount_paid += amount
        payment.payment_date = timezone.now()
        
        # Update status based on amount
        if payment.amount_paid >= payment.amount_due:
            payment.status = 'paid'
        elif payment.amount_paid > 0:
            payment.status = 'partial'
        
        payment.save()
        
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


@login_required
@require_http_methods(["POST"])
def mark_as_paid(request, payment_id):
    """
    تسديد الدفعة بالكامل
    """
    try:
        payment = Payment.objects.get(pk=payment_id)
        
        payment.amount_paid = payment.amount_due
        payment.status = 'paid'
        payment.payment_date = timezone.now()
        payment.save()
        
        return JsonResponse({
            'success': True,
            'message': 'تم تسديد الدفعة بنجاح',
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
