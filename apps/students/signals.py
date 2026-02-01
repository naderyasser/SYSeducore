"""
Signals for Student app - Auto-generate QR codes and student codes
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Student


@receiver(pre_save, sender=Student)
def auto_generate_student_code(sender, instance, **kwargs):
    """
    Auto-generate sequential student_code if not provided.
    Generates codes like: 1001, 1002, 1003...
    """
    if not instance.student_code:
        # Get the last student code
        last_student = Student.objects.order_by('-student_code').first()
        
        if last_student and last_student.student_code.isdigit():
            # Increment last code
            last_code = int(last_student.student_code)
            new_code = str(last_code + 1)
        else:
            # Start from 1001
            new_code = "1001"
        
        instance.student_code = new_code


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

