from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import Payment
from .services import SettlementService
from apps.teachers.models import Teacher
import logging

logger = logging.getLogger(__name__)


@login_required
def payment_list(request):
    """
    List all payments.
    """
    payments = Payment.objects.select_related('student').all()
    return render(request, 'payments/list.html', {'payments': payments})


@login_required
def payment_create(request):
    """
    Redirect to payment list - payments are created automatically via student enrollment.
    Manual payment recording is done through the student detail or admin interface.
    """
    from django.contrib import messages
    messages.info(request, 'يتم إنشاء المدفوعات تلقائياً عند تسجيل الطلاب. يرجى استخدام لوحة التحكم لتسجيل الدفعات اليدوية.')
    return redirect('payments:list')


@login_required
def settlement_list(request):
    """
    List all teachers with links to their settlement pages.
    """
    teachers = Teacher.objects.filter(is_active=True)
    return render(request, 'payments/settlement_list.html', {'teachers': teachers})


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
        payment = get_object_or_404(Payment, pk=payment_id)
        amount = float(request.POST.get('amount', 0))
        
        if amount <= 0:
            return JsonResponse({'success': False, 'error': 'Invalid amount'}, status=400)
        
        payment.amount_paid += amount
        payment.payment_date = timezone.now()
        
        # Update status based on amount
        if payment.amount_paid >= payment.amount_due:
            payment.status = 'paid'
        elif payment.amount_paid > 0:
            payment.status = 'partial'
        
        payment.save(update_fields=['amount_paid', 'payment_date', 'status'])
        
        return JsonResponse({'success': True, 'new_amount_paid': float(payment.amount_paid)})
    except Payment.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Payment not found'}, status=404)
    except (ValueError, TypeError) as e:
        return JsonResponse({'success': False, 'error': 'Invalid amount format'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'Internal server error'}, status=500)
