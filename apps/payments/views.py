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
    List all payments with filtering and stats.
    """
    from django.core.paginator import Paginator
    from django.db.models import Q, Sum, Count

    payments = Payment.objects.select_related('student', 'group').all()

    # Apply filters
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    month_filter = request.GET.get('month', '')

    if search:
        payments = payments.filter(
            Q(student__full_name__icontains=search) |
            Q(student__student_code__icontains=search)
        )

    if status_filter:
        payments = payments.filter(status=status_filter)

    if month_filter:
        try:
            year, month = month_filter.split('-')
            payments = payments.filter(month__year=int(year), month__month=int(month))
        except ValueError:
            pass

    # Calculate stats
    stats = {
        'paid_count': Payment.objects.filter(status='paid').count(),
        'partial_count': Payment.objects.filter(status='partial').count(),
        'unpaid_count': Payment.objects.filter(status='unpaid').count(),
        'total_collected': Payment.objects.aggregate(total=Sum('amount_paid'))['total'] or 0,
    }

    # Order and paginate
    payments = payments.order_by('-month', '-payment_date')
    paginator = Paginator(payments, 25)
    page = request.GET.get('page', 1)
    payments = paginator.get_page(page)

    return render(request, 'payments/list.html', {
        'payments': payments,
        'stats': stats,
    })


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
