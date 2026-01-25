from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import Payment
from .services import SettlementService
from apps.teachers.models import Teacher


@login_required
def payment_list(request):
    """
    List all payments.
    """
    payments = Payment.objects.select_related('student').all()
    return render(request, 'payments/list.html', {'payments': payments})


@login_required
def teacher_settlement(request, teacher_id):
    """
    Show teacher settlement for a specific month.
    """
    teacher = get_object_or_404(Teacher, pk=teacher_id)
    
    if request.method == 'POST':
        year = int(request.POST.get('year', timezone.now().year))
        month = int(request.POST.get('month', timezone.now().month))
        
        result = SettlementService.calculate_teacher_settlement(teacher_id, year, month)
        
        if result['success']:
            return render(request, 'payments/settlement.html', {
                'teacher': teacher,
                'settlement': result['data']
            })
        else:
            return JsonResponse(result, status=400)
    
    return render(request, 'payments/settlement.html', {'teacher': teacher})


@login_required
@require_http_methods(["POST"])
def record_payment(request, payment_id):
    """
    Record a payment for a student.
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
        
        return JsonResponse({'success': True, 'new_amount_paid': float(payment.amount_paid)})
    except Payment.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Payment not found'}, status=404)
