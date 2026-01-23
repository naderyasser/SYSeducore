"""
Barcode Generator Utility
Generates barcodes for students using python-barcode library
"""

import barcode
from barcode.writer import ImageWriter
from io import BytesIO
import os
from django.conf import settings


class BarcodeGenerator:
    """
    Barcode Generator for creating student barcodes
    """
    
    # Supported barcode formats
    CODE128 = 'code128'
    CODE39 = 'code39'
    EAN13 = 'ean13'
    
    def __init__(self, format_type=CODE128):
        """
        Initialize barcode generator
        
        Args:
            format_type: Barcode format type (default: code128)
        """
        self.format_type = format_type
        self.writer = ImageWriter()
        
        # Set default options
        self.writer.set_options({
            'module_width': 0.2,
            'module_height': 15.0,
            'font_size': 10,
            'text_distance': 5.0,
            'center_text': True,
        })
    
    def generate_barcode(self, data, filename=None, save_path=None):
        """
        Generate barcode for given data
        
        Args:
            data: Data to encode in barcode (e.g., student ID or custom barcode)
            filename: Output filename (optional)
            save_path: Path to save the barcode image (optional)
            
        Returns:
            BytesIO object containing the barcode image
        """
        try:
            # Get barcode class
            barcode_class = barcode.get_barcode_class(self.format_type)
            
            # Create barcode
            barcode_obj = barcode_class(data, writer=self.writer)
            
            # Generate image
            buffer = BytesIO()
            barcode_obj.write(buffer)
            buffer.seek(0)
            
            # Save to file if path provided
            if save_path:
                if not filename:
                    filename = f"{data}.png"
                
                full_path = os.path.join(save_path, filename)
                os.makedirs(save_path, exist_ok=True)
                
                with open(full_path, 'wb') as f:
                    f.write(buffer.getvalue())
            
            return buffer
            
        except Exception as e:
            raise Exception(f"Error generating barcode: {str(e)}")
    
    def generate_student_barcode(self, student_id, student_name=None):
        """
        Generate barcode for a student
        
        Args:
            student_id: Student ID to encode in barcode
            student_name: Student name (optional, used for filename)
            
        Returns:
            BytesIO object containing the barcode image
        """
        # Use student ID as barcode data
        data = str(student_id)
        
        # Generate filename
        filename = f"student_{data}.png"
        
        # Save path
        save_path = os.path.join(settings.MEDIA_ROOT, 'barcodes', 'students')
        
        return self.generate_barcode(data, filename, save_path)
    
    def generate_batch_barcodes(self, students):
        """
        Generate barcodes for multiple students
        
        Args:
            students: List of student dictionaries or objects
            
        Returns:
            Dictionary mapping student IDs to barcode file paths
        """
        results = {}
        
        for student in students:
            try:
                # Get student ID
                if isinstance(student, dict):
                    student_id = student.get('id')
                else:
                    student_id = student.id
                
                # Generate barcode
                barcode_buffer = self.generate_student_barcode(student_id)
                
                # Store result
                results[student_id] = barcode_buffer
                
            except Exception as e:
                print(f"Error generating barcode for student {student_id}: {str(e)}")
                results[student_id] = None
        
        return results
    
    def validate_barcode(self, barcode_data):
        """
        Validate barcode data
        
        Args:
            barcode_data: Barcode data to validate
            
        Returns:
            Boolean indicating if barcode is valid
        """
        try:
            # Check if barcode data is not empty
            if not barcode_data or not str(barcode_data).strip():
                return False
            
            # Check if barcode contains only valid characters
            valid_chars = set('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-')
            barcode_str = str(barcode_data).upper()
            
            return all(c in valid_chars for c in barcode_str)
            
        except Exception:
            return False
    
    def get_barcode_url(self, student_id):
        """
        Get URL for student barcode image
        
        Args:
            student_id: Student ID
            
        Returns:
            URL path to the barcode image
        """
        filename = f"student_{student_id}.png"
        return f"{settings.MEDIA_URL}barcodes/students/{filename}"


# Convenience functions
def generate_student_barcode(student_id, student_name=None):
    """
    Convenience function to generate student barcode
    
    Args:
        student_id: Student ID
        student_name: Student name (optional)
        
    Returns:
        BytesIO object containing the barcode image
    """
    generator = BarcodeGenerator()
    return generator.generate_student_barcode(student_id, student_name)


def validate_barcode(barcode_data):
    """
    Convenience function to validate barcode
    
    Args:
        barcode_data: Barcode data to validate
        
    Returns:
        Boolean indicating if barcode is valid
    """
    generator = BarcodeGenerator()
    return generator.validate_barcode(barcode_data)
