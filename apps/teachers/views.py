from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Teacher, Group


@login_required
def teacher_list(request):
    """
    List all teachers.
    """
    teachers = Teacher.objects.filter(is_active=True)
    return render(request, 'teachers/list.html', {'teachers': teachers})


@login_required
def teacher_detail(request, teacher_id):
    """
    Show teacher details.
    """
    teacher = Teacher.objects.get(pk=teacher_id)
    groups = teacher.groups.filter(is_active=True)
    return render(request, 'teachers/detail.html', {'teacher': teacher, 'groups': groups})
