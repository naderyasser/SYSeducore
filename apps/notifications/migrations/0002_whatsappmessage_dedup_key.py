from django.db import migrations, models


class Migration(migrations.Migration):
    """
    BUG-05 / PERF-03: give every automated WhatsApp send an idempotency key.

    The attendance cron used to re-send the same message every 5 minutes all
    day because nothing recorded *per student* that the message had already
    gone out. ``dedup_key`` is reserved (a unique INSERT) before the API call,
    so a retried task, an overlapping beat tick or a restarted worker can
    never deliver the same message — or pay for it — twice.
    """

    dependencies = [
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='whatsappmessage',
            name='dedup_key',
            field=models.CharField(
                blank=True,
                help_text='مفتاح فريد يمنع إرسال نفس الرسالة أكثر من مرة',
                max_length=150,
                null=True,
                unique=True,
                verbose_name='مفتاح منع التكرار',
            ),
        ),
    ]
