"""
Drop the never-implemented ``per_session`` financial status (audit DATA-10).

``Student.get_monthly_fee_for_group`` fell through to ``group.standard_fee``
for ``per_session`` and ``AttendanceService.check_financial_status`` treated it
as ``normal``, so those students have always been billed a full month. Rewriting
the rows to ``normal`` therefore changes no money — it just makes the stored
value match the behaviour that was already in effect.
"""
from django.db import migrations, models


def per_session_to_normal(apps, schema_editor):
    StudentGroupEnrollment = apps.get_model('students', 'StudentGroupEnrollment')
    StudentGroupEnrollment.objects.filter(
        financial_status='per_session'
    ).update(financial_status='normal')


def noop_reverse(apps, schema_editor):
    """Irreversible in data terms: 'normal' rows cannot be told apart afterwards."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0011_studentgroupenrollment_cycle_end_date_and_more"),
    ]

    operations = [
        migrations.RunPython(per_session_to_normal, noop_reverse),
        migrations.AlterField(
            model_name="studentgroupenrollment",
            name="financial_status",
            field=models.CharField(
                choices=[
                    ("normal", "عادي"),
                    ("symbolic", "مبلغ رمزي"),
                    ("exempt", "إعفاء كامل"),
                ],
                default="normal",
                max_length=15,
                verbose_name="الحالة المالية",
            ),
        ),
    ]
