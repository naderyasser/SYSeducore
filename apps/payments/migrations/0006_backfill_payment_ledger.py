"""
Backfill the payment audit trail.

1. Flag existing zero-fee rows as ``is_exempt`` so they stop counting as
   real collections (they were created with ``status='paid'`` and
   ``amount_due=0`` for exempt enrollments).
2. Give every payment that already carries an ``amount_paid`` an explicit
   opening-balance :class:`PaymentTransaction`, so ``amount_paid`` is
   reconciled from the ledger from now on instead of being an unexplained
   running total.
"""
from decimal import Decimal

from django.db import migrations

OPENING_NOTE = 'رصيد افتتاحي — ترحيل بيانات ما قبل سجل الحركات'


def backfill(apps, schema_editor):
    Payment = apps.get_model('payments', 'Payment')
    PaymentTransaction = apps.get_model('payments', 'PaymentTransaction')

    # 1. Zero-fee rows are exemptions, not collections.
    Payment.objects.filter(amount_due__lte=Decimal('0')).update(is_exempt=True)

    # 2. Opening balances for money already recorded.
    already = set(
        PaymentTransaction.objects.values_list('payment_id', flat=True)
    )
    batch = []
    qs = Payment.objects.filter(amount_paid__gt=Decimal('0')).only(
        'payment_id', 'amount_paid'
    )
    for payment in qs.iterator(chunk_size=500):
        if payment.pk in already:
            continue
        batch.append(PaymentTransaction(
            payment_id=payment.pk,
            amount=payment.amount_paid,
            kind='opening',
            created_by=None,
            note=OPENING_NOTE,
        ))
        if len(batch) >= 500:
            PaymentTransaction.objects.bulk_create(batch)
            batch = []
    if batch:
        PaymentTransaction.objects.bulk_create(batch)


def unbackfill(apps, schema_editor):
    PaymentTransaction = apps.get_model('payments', 'PaymentTransaction')
    PaymentTransaction.objects.filter(kind='opening', note=OPENING_NOTE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0005_payment_created_by_payment_is_exempt_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
