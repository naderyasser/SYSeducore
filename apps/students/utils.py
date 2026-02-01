"""
QR Code Generation Utility for Student Attendance System
"""
import qrcode
import qrcode.image.svg
from io import BytesIO
from django.core.files.base import ContentFile
from django.conf import settings
import os


class QRCodeGenerator:
    """
    QR Code Generator for Student ID Cards
    
    Features:
    - Generates QR codes containing student_code only
    - Stores as base64 for database storage
    - Supports printable format for ID cards (2cm x 2cm)
    - Can include school logo in QR design
    """
    
    # QR Code configuration
    QR_SIZE = 200  # pixels (approx 2cm at 96 DPI)
    QR_BORDER = 4  # quiet zone
    QR_ERROR_CORRECTION = qrcode.constants.ERROR_CORRECT_H  # High error correction
    
    @staticmethod
    def generate_qr_code_base64(student_code, include_logo=False):
        """
        Generate QR code as base64 string for database storage
        
        Args:
            student_code: Student's unique code (e.g., "1001")
            include_logo: Whether to include school logo in center
            
        Returns:
            base64 string of QR code image
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=QRCodeGenerator.QR_ERROR_CORRECTION,
            box_size=10,
            border=QRCodeGenerator.QR_BORDER,
        )
        
        # Add student code as data
        qr.add_data(str(student_code))
        qr.make(fit=True)
        
        # Create QR code image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Add logo in center if requested
        if include_logo:
            img = QRCodeGenerator._add_logo_to_qr(img)
        
        # Convert to base64
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        img_str = buffer.getvalue()
        
        # Encode to base64
        import base64
        img_base64 = base64.b64encode(img_str).decode('utf-8')
        
        return f"data:image/png;base64,{img_base64}"
    
    @staticmethod
    def generate_qr_code_image(student_code, include_logo=False):
        """
        Generate QR code as PIL Image for PDF printing
        
        Args:
            student_code: Student's unique code
            include_logo: Whether to include school logo
            
        Returns:
            PIL Image object
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=QRCodeGenerator.QR_ERROR_CORRECTION,
            box_size=10,
            border=QRCodeGenerator.QR_BORDER,
        )
        
        qr.add_data(str(student_code))
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        if include_logo:
            img = QRCodeGenerator._add_logo_to_qr(img)
        
        return img
    
    @staticmethod
    def _add_logo_to_qr(qr_img):
        """
        Add school logo to center of QR code
        
        Args:
            qr_img: QR code PIL Image
            
        Returns:
            Combined PIL Image
        """
        try:
            from PIL import Image
            
            # Path to school logo
            logo_path = os.path.join(
                settings.BASE_DIR, 
                'static', 
                'images', 
                'school-logo.png'
            )
            
            if not os.path.exists(logo_path):
                # Try alternative logo paths
                alternative_paths = [
                    os.path.join(settings.BASE_DIR, 'static', 'logo.png'),
                    os.path.join(settings.MEDIA_ROOT, 'logo.png'),
                ]
                for path in alternative_paths:
                    if os.path.exists(path):
                        logo_path = path
                        break
                else:
                    # No logo found, return QR as is
                    return qr_img
            
            # Open logo
            logo = Image.open(logo_path)
            
            # Calculate logo size (about 20% of QR size)
            qr_width, qr_height = qr_img.size
            logo_size = int(min(qr_width, qr_height) * 0.2)
            
            # Resize logo
            logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
            
            # Convert to RGBA if needed
            if logo.mode != 'RGBA':
                logo = logo.convert('RGBA')
            
            # Calculate position (center)
            pos = (
                (qr_width - logo_size) // 2,
                (qr_height - logo_size) // 2
            )
            
            # Paste logo onto QR
            qr_img = qr_img.convert('RGBA')
            qr_img.paste(logo, pos, logo)
            
            # Convert back to RGB
            return qr_img.convert('RGB')
            
        except Exception as e:
            # If logo addition fails, return QR as is
            print(f"Warning: Could not add logo to QR: {e}")
            return qr_img
    
    @staticmethod
    def generate_qr_for_student(student):
        """
        Generate and save QR code for a student
        
        Args:
            student: Student model instance
            
        Returns:
            base64 string of QR code
        """
        return QRCodeGenerator.generate_qr_code_base64(
            student.student_code,
            include_logo=True
        )
    
    @staticmethod
    def regenerate_qr_for_student(student):
        """
        Regenerate QR code for existing student
        
        Args:
            student: Student model instance
            
        Returns:
            base64 string of new QR code
        """
        student.qr_code_base64 = QRCodeGenerator.generate_qr_for_student(student)
        student.save(update_fields=['qr_code_base64'])
        return student.qr_code_base64


def generate_student_qr_code(sender, instance, created, **kwargs):
    """
    Signal handler to auto-generate QR code on student creation
    """
    if created:
        from .models import Student
        if isinstance(instance, Student):
            if not instance.qr_code_base64:
                instance.qr_code_base64 = QRCodeGenerator.generate_qr_for_student(instance)
                instance.save(update_fields=['qr_code_base64'])
