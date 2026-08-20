from django.http import JsonResponse

from apps.accounts.decorators import ajax_login_required

from .models import Group


@ajax_login_required
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

    qs = (
        Group.objects.filter(is_active=True)
        .select_related('teacher')
        .prefetch_related('schedules', 'teacher__subjects')
    )

    if stage:
        qs = qs.filter(education_stage=stage)
    if grade:
        qs = qs.filter(education_year=grade)
    if teacher_id:
        try:
            qs = qs.filter(teacher_id=int(teacher_id))
        except (TypeError, ValueError):
            # Not a real id — no group can match it, so the queryset is left
            # empty instead of raising ``ValueError`` (a 500 to a JSON caller).
            qs = qs.none()
    if subject_id:
        try:
            qs = qs.filter(teacher__subjects__pk=int(subject_id)).distinct()
        except (TypeError, ValueError):
            qs = qs.none()

    results = []
    for g in qs.order_by('group_name'):
        teacher_name = g.teacher.full_name if g.teacher else '-'
        subjects = ', '.join(
            s.name for s in g.teacher.subjects.all()
        ) if g.teacher else '-'
        # كل مواعيد المجموعة، لا اليوم الأول فقط (GroupSchedule هو المصدر)
        schedule = ' ، '.join(
            f"{entry.get_day_display()} {entry.start_time.strftime('%I:%M %p')}"
            for entry in g.get_schedule_entries()
        ) or '-'
        label = f"{teacher_name} — {subjects} — {schedule}"
        results.append({'id': g.group_id, 'label': label})

    return JsonResponse(results, safe=False)
