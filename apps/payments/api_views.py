from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
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
            'new_amount_paid': float(payment.amount_paid)
        })
    except Payment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Payment not found'
        }, status=404)
