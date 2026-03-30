from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Q
from .models import Payment
from .services import SettlementService
from apps.teachers.models import Teacher, Group
from apps.attendance.models import ActivityLog
from apps.students.models import Student


@login_required
def payment_list(request):
    """
    List payments with filters. Defaults to current month unpaid/partial.
    """
    current_month = timezone.now().date().replace(day=1)

    # Filter params
    month_filter = request.GET.get('month', current_month.strftime('%Y-%m'))
    status_filter = request.GET.get('status', '')
    group_filter = request.GET.get('group', '')
    search = request.GET.get('search', '')

    try:
        filter_year, filter_month = int(month_filter[:4]), int(month_filter[5:7])
        from datetime import date
        month_date = date(filter_year, filter_month, 1)
    except Exception:
        month_date = current_month

    payments = Payment.objects.select_related('student', 'group', 'group__teacher').filter(month=month_date)

    if status_filter:
        payments = payments.filter(status=status_filter)
    if group_filter:
        payments = payments.filter(group_id=group_filter)
    if search:
        payments = payments.filter(
            Q(student__full_name__icontains=search) |
            Q(student__student_code__icontains=search) |
            Q(student__parent_phone__icontains=search)
        )

    payments = payments.order_by('status', 'student__full_name')

    # Stats for current month
    all_month_payments = Payment.objects.filter(month=month_date)
    stats = {
        'paid': all_month_payments.filter(status='paid').count(),
        'partial': all_month_payments.filter(status='partial').count(),
        'unpaid': all_month_payments.filter(status='unpaid').count(),
        'total': all_month_payments.count(),
    }

    groups = Group.objects.filter(is_active=True).select_related('teacher')

    context = {
        'payments': payments,
        'stats': stats,
        'groups': groups,
        'current_month': month_date,
        'month_filter': month_filter,
        'status_filter': status_filter,
        'group_filter': group_filter,
        'search': search,
    }
    return render(request, 'payments/list.html', context)


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

        ActivityLog.log(
            user=request.user, action='payment_record',
            description=f'تسجيل دفعة: {amount} جنيه للطالب {payment.student.full_name}',
            target_model='Payment', target_id=payment.pk, request=request
        )

        return JsonResponse({'success': True, 'new_amount_paid': float(payment.amount_paid)})
    except Payment.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Payment not found'}, status=404)
