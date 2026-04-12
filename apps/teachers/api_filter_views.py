from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

from .models import Group


@login_required
def groups_filter_api(request):
    """
    API: فلترة المجموعات حسب المرحلة / السنة / المادة / المدرس
    GET /api/groups/filter/?stage=&grade=&subject_id=&teacher_id=
    Returns [{id, label}]
    """
    stage = request.GET.get('stage', '').strip()
    grade = request.GET.get('grade', '').strip()
    subject_id = request.GET.get('subject_id', '').strip()
    teacher_id = request.GET.get('teacher_id', '').strip()

    qs = Group.objects.filter(is_active=True).select_related('teacher', 'room')

    if stage:
        qs = qs.filter(education_stage=stage)
    if grade:
        qs = qs.filter(education_year=grade)
    if teacher_id:
        qs = qs.filter(teacher_id=teacher_id)
    if subject_id:
        qs = qs.filter(teacher__subjects__pk=subject_id).distinct()

    results = []
    for g in qs.order_by('group_name'):
        teacher_name = g.teacher.full_name if g.teacher else '-'
        subjects = ', '.join(
            s.name for s in g.teacher.subjects.all()
        ) if g.teacher else '-'
        day = g.get_schedule_day_display()
        time = g.schedule_time.strftime('%I:%M %p') if g.schedule_time else ''
        label = f"{teacher_name} — {subjects} — {day} {time}"
        results.append({'id': g.group_id, 'label': label})

    return JsonResponse(results, safe=False)
