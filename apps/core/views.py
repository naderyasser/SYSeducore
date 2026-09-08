"""
Project-wide quick search: one box, three kinds of thing.

The desk's complaint was the number of steps between "I need Mr. Ahmed's
groups" and seeing them: open the teachers screen, find the row, open it,
find the groups. Typing the name here and picking the result goes straight
to the page. The filters are the same ones the directory screens already use
(``teacher_list``, ``group_list``, ``students_list_api``), so a name that
finds someone there finds them here.
"""
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_GET
from django_ratelimit.decorators import ratelimit

from apps.accounts.decorators import ratelimit_key
from apps.students.models import Student
from apps.teachers.models import Group, Teacher

#: Per kind. A dropdown is for jumping, not browsing: past this many the
#: directory screen with its full list is the better tool, and the response
#: says so.
LIMIT = 6
MIN_CHARS = 2


def _teachers(term):
    rows = (
        Teacher.objects.filter(
            Q(full_name__icontains=term)
            | Q(phone__icontains=term)
            | Q(subjects__name__icontains=term)
        )
        .distinct()
        .order_by('full_name')[: LIMIT + 1]
    )
    return [
        {
            'label': t.full_name,
            'hint': t.phone,
            'url': reverse('teachers:detail', kwargs={'teacher_id': t.pk}),
        }
        for t in rows
    ]


def _groups(term):
    rows = (
        Group.objects.filter(
            Q(group_name__icontains=term)
            | Q(teacher__full_name__icontains=term)
            | Q(teacher__subjects__name__icontains=term)
        )
        .select_related('teacher')
        .distinct()
        .order_by('-is_active', 'group_name')[: LIMIT + 1]
    )
    return [
        {
            'label': g.group_name,
            'hint': g.teacher.full_name if g.teacher_id else '',
            'inactive': not g.is_active,
            'url': reverse('teachers:group_detail', kwargs={'group_id': g.pk}),
        }
        for g in rows
    ]


def _students(term):
    rows = (
        Student.objects.filter(
            Q(full_name__icontains=term)
            | Q(student_code__icontains=term)
            | Q(parent_phone__icontains=term)
            | Q(student_phone__icontains=term)
        )
        .order_by('-is_active', 'full_name')[: LIMIT + 1]
    )
    return [
        {
            'label': s.full_name,
            'hint': s.student_code,
            'inactive': not s.is_active,
            'url': reverse('students:detail', kwargs={'student_id': s.pk}),
        }
        for s in rows
    ]


@login_required
@require_GET
@ratelimit(key=ratelimit_key, rate='300/m', method='GET', block=False)
def quick_search(request):
    """
    ``GET /api/quick-search/?q=`` → ``{"groups": [...], "teachers": [...],
    "students": [...]}``, each capped at :data:`LIMIT` with a ``more`` flag.

    Fires on every keystroke, hence the rate limit. The bucket is per client
    IP (``ratelimit_key``), and a centre's whole desk sits behind one router,
    so the rate has to cover several people typing at once — 300/min does;
    a stuck key is already collapsed by the 200ms debounce in the browser.
    ``block=False`` on purpose: with ``block=True`` a throttled request raises
    ``Ratelimited`` (a ``PermissionDenied``), which the project's 403 handler
    turns into an HTML page — and a fetch() reading a 403 as "session gone"
    would bounce a logged-in user off whatever screen they were on. A JSON
    429 lets the box say "try again in a moment" instead.
    """
    if getattr(request, 'limited', False):
        return JsonResponse(
            {'error': 'محاولات كثيرة في وقت قصير، حاول بعد لحظة'}, status=429
        )
    term = (request.GET.get('q') or '').strip()
    if len(term) < MIN_CHARS:
        return JsonResponse({'q': term, 'groups': [], 'teachers': [], 'students': []})

    def capped(items):
        return {'items': items[:LIMIT], 'more': len(items) > LIMIT}

    return JsonResponse({
        'q': term,
        'groups': capped(_groups(term)),
        'teachers': capped(_teachers(term)),
        'students': capped(_students(term)),
        # urlencode, not concatenation: a term with "&" or "#" would
        # otherwise cut its own link short.
        'more_urls': {
            'groups': reverse('teachers:group_list') + '?' + urlencode({'q': term}),
            'teachers': reverse('teachers:list') + '?' + urlencode({'q': term}),
            'students': reverse('students:list') + '?' + urlencode({'search': term}),
        },
    })
