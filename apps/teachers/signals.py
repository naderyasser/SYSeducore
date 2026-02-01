from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Teacher


@receiver(post_save, sender=Teacher)
def generate_teacher_qr_on_create(sender, instance, created, **kwargs):
    """
    Automatically generate QR code for teacher when created.
    """
    if created and not instance.qr_code_base64:
        # Avoid recursion by checking if QR already exists
        instance.generate_qr_code()
