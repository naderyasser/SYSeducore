from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Student
from .forms import StudentForm
from apps.teachers.models import Group
from apps.accounts.decorators import supervisor_required


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
