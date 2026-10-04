"""
حذف نهائي «فعلي» من سلة المهملات: العنصر وكل سجلاته (مدفوعات وحركاتها،
حضور، استثناءات، باقات، تسجيلات، حصص ودورات المجموعة) — مش بس الخانة.

Only the admin calls this, from the recycle bin, after a second confirmation
that lists what goes with it. An APPROVED teacher settlement is never touched:
its lines are the record of money already handed to a teacher, so purging is
refused until that sheet is reopened. Draft sheets lose the lines and have
their totals recalculated.
"""
from django.db import transaction

from apps.attendance.models import Attendance, ExceptionRecord, Session
from apps.payments.models import (
    Payment, PaymentPackage, TeacherSettlement, TeacherSettlementLine,
)
from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.models import Group, GroupCycle, Teacher


class PurgeRefused(Exception):
    pass


def _drop_settlement_lines(lines):
    approved = lines.filter(settlement__status=TeacherSettlement.STATUS_APPROVED)
    if approved.exists():
        names = ', '.join(sorted({str(l.settlement.teacher.full_name) for l in approved.select_related('settlement__teacher')}))
        raise PurgeRefused(f'مرتبط بكشف تصفية معتمد ({names}) — افتح الكشف الأول')
    settlements = list(TeacherSettlement.objects.filter(lines__in=lines).distinct())
    lines.delete()
    for s in settlements:
        s.recalculate_totals()


def records_summary(kind, obj):
    """What a purge of ``obj`` would take with it — shown in the confirmation."""
    if kind == 'student':
        return {
            'payments': Payment.objects.filter(student=obj).count(),
            'attendance': Attendance.objects.filter(student=obj).count(),
        }
    if kind == 'group':
        return {
            'payments': Payment.objects.filter(group=obj).count(),
            'attendance': Attendance.objects.filter(session__group=obj).count(),
        }
    if kind == 'teacher':
        return {
            'payments': Payment.objects.filter(group__teacher=obj).count(),
            'attendance': Attendance.objects.filter(session__group__teacher=obj).count(),
        }
    return {'payments': 0, 'attendance': 0}


@transaction.atomic
def purge_student(student):
    _drop_settlement_lines(TeacherSettlementLine.objects.filter(student=student))
    Attendance.objects.filter(student=student).delete()
    ExceptionRecord.objects.filter(student=student).delete()
    Payment.objects.filter(student=student).delete()          # transactions cascade
    PaymentPackage.objects.filter(student=student).delete()
    StudentGroupEnrollment.objects.filter(student=student).delete()
    Student.all_objects.filter(pk=student.pk).hard_delete()


@transaction.atomic
def purge_group(group):
    _drop_settlement_lines(TeacherSettlementLine.objects.filter(group=group))
    Attendance.objects.filter(session__group=group).delete()
    ExceptionRecord.objects.filter(group=group).delete()
    Payment.objects.filter(group=group).delete()
    PaymentPackage.objects.filter(group=group).delete()
    StudentGroupEnrollment.objects.filter(group=group).delete()
    Session.objects.filter(group=group).delete()
    GroupCycle.objects.filter(group=group).delete()
    Group.all_objects.filter(pk=group.pk).hard_delete()        # schedules cascade


@transaction.atomic
def purge_teacher(teacher):
    for group in Group.all_objects.filter(teacher=teacher):
        purge_group(group)
    if TeacherSettlement.objects.filter(teacher=teacher, status=TeacherSettlement.STATUS_APPROVED).exists():
        raise PurgeRefused('المدرس عنده كشف تصفية معتمد — افتحه الأول')
    TeacherSettlement.objects.filter(teacher=teacher).delete()
    Teacher.all_objects.filter(pk=teacher.pk).hard_delete()


PURGERS = {'student': purge_student, 'group': purge_group, 'teacher': purge_teacher}
