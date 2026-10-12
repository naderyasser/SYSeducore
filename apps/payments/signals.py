"""
A payment whose money moved refreshes the draft settlement it feeds — see
:func:`apps.payments.sync.payment_changed`. Saves that only touch the session
counter (every scan writes ``sessions_attended``) are skipped, and so are
invoices created or deleted with nothing paid on them: a settlement's money
is what was paid, and its session columns are recomputed whenever the sheet
is opened.
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Payment
from .sync import MONEY_FIELDS, payment_changed


@receiver(post_save, sender=Payment, dispatch_uid='payments.payment_saved')
def payment_saved(sender, instance, created, update_fields=None, raw=False, **kwargs):
    if raw:
        return
    # A settlement counts what was *paid*: a brand-new invoice with nothing
    # on it (the scanner and the payments page open them in batches) moves
    # no money, and its line appears the next time the sheet is opened.
    if created and not instance.amount_paid:
        return
    if not created and update_fields is not None and not (set(update_fields) & MONEY_FIELDS):
        return
    payment_changed(instance)


@receiver(post_delete, sender=Payment, dispatch_uid='payments.payment_deleted')
def payment_deleted(sender, instance, **kwargs):
    if instance.amount_paid:
        payment_changed(instance)
