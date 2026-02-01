from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.db.models import Q, Count
from .models import Student, StudentGroupEnrollment
from .forms import StudentForm
from .utils import QRCodeGenerator
from apps.teachers.models import Group
from apps.accounts.decorators import supervisor_required
import io

# Import weasyprint conditionally (requires GTK binaries on Windows)
try:
    from weasyprint import HTML
    HAS_WEASYPRINT = True
except (ImportError, OSError):
    HAS_WEASYPRINT = False


@login_required
def student_list(request):
    """
    List all students with advanced filtering and statistics.
    """
    # Get filter parameters
    search = request.GET.get('search', '')
    group_id = request.GET.get('group', '')
    status = request.GET.get('status', 'all')
    
    # Base queryset with prefetch
    students = Student.objects.prefetch_related(
        'studentgroupenrollment_set__group',
        'groups'
    ).order_by('full_name')
    
    # Apply filters
    if search:
        students = students.filter(
            Q(full_name__icontains=search) |
            Q(student_code__icontains=search) |
            Q(parent_phone__icontains=search)
        )
    
    if group_id:
        students = students.filter(groups__group_id=group_id)
    
    if status == 'active':
        students = students.filter(is_active=True)
    elif status == 'inactive':
        students = students.filter(is_active=False)
    
    # Statistics
    all_students = Student.objects.all()
    total_students = all_students.count()
    active_students = all_students.filter(is_active=True).count()
    students_with_qr = all_students.exclude(qr_code_base64__isnull=True).exclude(qr_code_base64='').count()
    
    # New this month
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    new_this_month = all_students.filter(created_at__gte=month_start).count()
    
    # Get groups for filter
    groups = Group.objects.filter(is_active=True).select_related('teacher')
    
    context = {
        'students': students,
        'groups': groups,
        'total_students': total_students,
        'active_students': active_students,
        'students_with_qr': students_with_qr,
        'new_this_month': new_this_month,
        'current_filters': {
            'search': search,
            'group': group_id,
            'status': status,
        }
    }
    
    return render(request, 'students/list_new.html', context)


@login_required
def student_detail(request, student_id):
    """
    Show student details.
    """
    student = get_object_or_404(Student, pk=student_id)
    return render(request, 'students/detail.html', {'student': student})


@supervisor_required
def student_create(request):
    """
    Create a new student.
    """
    groups = Group.objects.filter(is_active=True).select_related('teacher')

    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم إضافة الطالب بنجاح')
            return redirect('students:list')
    else:
        form = StudentForm()

    return render(request, 'students/form.html', {'form': form, 'groups': groups})


@supervisor_required
def student_update(request, student_id):
    """
    Update an existing student.
    """
    student = get_object_or_404(Student, pk=student_id)
    groups = Group.objects.filter(is_active=True).select_related('teacher')

    if request.method == 'POST':
        form = StudentForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تحديث بيانات الطالب بنجاح')
            return redirect('students:detail', student_id=student_id)
    else:
        form = StudentForm(instance=student)

    return render(request, 'students/form.html', {'form': form, 'student': student, 'groups': groups})


@login_required
def print_qr_codes(request):
    """
    Print QR codes for students
    - If all=true: Show selection page
    - If student_ids provided: Generate PDF
    """
    # Check if showing selection page
    if request.GET.get('all') == 'true' or not request.GET.get('student_ids'):
        # Show selection page
        students = Student.objects.filter(is_active=True).prefetch_related('groups')
        groups = Group.objects.filter(is_active=True).select_related('teacher')
        return render(request, 'students/qr_select.html', {
            'students': students,
            'groups': groups,
        })
    
    # Get student IDs from session or query parameter
    student_ids = request.session.get('qr_print_student_ids', [])
    
    if not student_ids and request.GET.get('student_ids'):
        # Parse comma-separated IDs from URL
        student_ids = [int(id) for id in request.GET.get('student_ids').split(',')]
    
    if not student_ids:
        messages.warning(request, 'لم يتم تحديد أي طلاب للطباعة')
        return redirect('students:print_qr_codes')
    
    # Get students
    students = Student.objects.filter(student_id__in=student_ids, is_active=True)
    
    # Generate QR codes for students who don't have them
    for student in students:
        if not student.qr_code_base64:
            student.generate_qr_code()
    
    # Clear session
    if 'qr_print_student_ids' in request.session:
        del request.session['qr_print_student_ids']
    
    # Render HTML template
    html_string = render_to_string('students/qr_print.html', {
        'students': students,
        'date': timezone.now().strftime('%Y-%m-%d'),
    })
    
    # Generate PDF
    html = HTML(string=html_string, base_url=request.build_absolute_uri())
    pdf_file = html.write_pdf()
    
    # Create response
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="qr_codes_{timezone.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
    
    return response


@login_required
def qr_card_single(request, student_id):
    """
    Print single student QR card
    """
    student = get_object_or_404(Student, pk=student_id, is_active=True)
    
    # Generate QR if not exists
    if not student.qr_code_base64:
        student.generate_qr_code()
    
    return render(request, 'students/qr_card_single.html', {
        'student': student
    })
