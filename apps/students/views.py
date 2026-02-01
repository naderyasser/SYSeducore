from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.template.loader import render_to_string
from .models import Student
from .forms import StudentForm
from .utils import QRCodeGenerator
from apps.teachers.models import Group
from apps.accounts.decorators import supervisor_required
from weasyprint import HTML
import io


@login_required
def student_list(request):
    """
    List all students.
    """
    students = Student.objects.filter(is_active=True)
    return render(request, 'students/list.html', {'students': students})


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
    Print QR codes for students as PDF
    Supports printing from admin action or direct URL
    """
    from django.utils import timezone
    
    # Get student IDs from session or query parameter
    student_ids = request.session.get('qr_print_student_ids', [])
    
    if not student_ids and request.GET.get('student_ids'):
        # Parse comma-separated IDs from URL
        student_ids = [int(id) for id in request.GET.get('student_ids').split(',')]
    
    if not student_ids:
        messages.warning(request, 'لم يتم تحديد أي طلاب للطباعة')
        return redirect('admin:students_student_changelist')
    
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
