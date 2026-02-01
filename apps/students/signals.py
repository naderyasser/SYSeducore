"""
Signals for Student app - Auto-generate QR codes
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Student


@receiver(post_save, sender=Student)
def generate_student_qr_code(sender, instance, created, **kwargs):
    """
    Auto-generate QR code when a student is created
    
    This signal is triggered after a student is saved.
    If the student is newly created and doesn't have a QR code,
    it will automatically generate one.
    """
    if created and not instance.qr_code_base64:
        try:
            instance.generate_qr_code()
        except Exception as e:
            # Log error but don't prevent student creation
            print(f"Warning: Could not generate QR code for student {instance.student_code}: {e}")
