"""
PDF Generator Utility
Generates PDF reports using reportlab library
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from io import BytesIO
import os
from datetime import datetime
from django.conf import settings


class PDFGenerator:
    """
    PDF Generator for creating reports
    """
    
    def __init__(self):
        """
        Initialize PDF generator
        """
        self.styles = getSampleStyleSheet()
        self._setup_arabic_font()
        
    def _setup_arabic_font(self):
        """
        Setup Arabic font for PDF generation
        """
        try:
            # Register Arabic font (you need to have an Arabic font file)
            font_path = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'ArabicFont.ttf')
            
            if os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont('Arabic', font_path))
                
                # Create Arabic styles
                self.styles.add(ParagraphStyle(
                    name='ArabicHeading',
                    parent=self.styles['Heading1'],
                    fontName='Arabic',
                    fontSize=18,
                    alignment=TA_RIGHT,
                    spaceAfter=20
                ))
                
                self.styles.add(ParagraphStyle(
                    name='ArabicNormal',
                    parent=self.styles['Normal'],
                    fontName='Arabic',
                    fontSize=10,
                    alignment=TA_RIGHT,
                    wordWrap='RTL'
                ))
        except Exception as e:
            print(f"Warning: Could not setup Arabic font: {str(e)}")
    
    def generate_pdf(self, data, filename=None):
        """
        Generate PDF from data
        
        Args:
            data: Dictionary containing report data
            filename: Output filename (optional)
            
        Returns:
            BytesIO object containing the PDF
        """
        buffer = BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )
        
        # Build PDF content
        elements = self._build_pdf_content(data)
        
        # Generate PDF
        doc.build(elements)
        
        buffer.seek(0)
        return buffer
    
    def _build_pdf_content(self, data):
        """
        Build PDF content elements
        
        Args:
            data: Report data dictionary
            
        Returns:
            List of PDF elements
        """
        elements = []
        
        # Add title
        title = data.get('title', 'تقرير')
        elements.append(Paragraph(title, self.styles['ArabicHeading']))
        elements.append(Spacer(1, 0.5*cm))
        
        # Add date
        date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elements.append(Paragraph(f'التاريخ: {date_str}', self.styles['ArabicNormal']))
        elements.append(Spacer(1, 0.5*cm))
        
        # Add summary if available
        if 'summary' in data:
            elements.append(Paragraph('الملخص:', self.styles['Heading2']))
            for key, value in data['summary'].items():
                elements.append(Paragraph(f'{key}: {value}', self.styles['ArabicNormal']))
            elements.append(Spacer(1, 0.5*cm))
        
        # Add table if available
        if 'table' in data:
            table_data = data['table']
            elements.append(self._create_table(table_data))
        
        return elements
    
    def _create_table(self, table_data):
        """
        Create PDF table
        
        Args:
            table_data: Dictionary containing headers and rows
            
        Returns:
            Table object
        """
        headers = table_data.get('headers', [])
        rows = table_data.get('rows', [])
        
        # Combine headers and rows
        data = [headers] + rows
        
        # Create table
        table = Table(data, repeatRows=1)
        
        # Add table style
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Arabic'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        
        return table
    
    def generate_attendance_report(self, data):
        """
        Generate attendance report PDF
        
        Args:
            data: Attendance report data
            
        Returns:
            BytesIO object containing the PDF
        """
        report_data = {
            'title': 'تقرير الحضور',
            'summary': data.get('summary', {}),
            'table': {
                'headers': data.get('headers', []),
                'rows': data.get('rows', [])
            }
        }
        
        return self.generate_pdf(report_data)
    
    def generate_payment_report(self, data):
        """
        Generate payment report PDF
        
        Args:
            data: Payment report data
            
        Returns:
            BytesIO object containing the PDF
        """
        report_data = {
            'title': 'تقرير المدفوعات',
            'summary': data.get('summary', {}),
            'table': {
                'headers': data.get('headers', []),
                'rows': data.get('rows', [])
            }
        }
        
        return self.generate_pdf(report_data)
    
    def generate_settlement_report(self, data):
        """
        Generate teacher settlement report PDF
        
        Args:
            data: Settlement report data
            
        Returns:
            BytesIO object containing the PDF
        """
        report_data = {
            'title': 'تقرير مستحقات المدرسين',
            'summary': data.get('summary', {}),
            'table': {
                'headers': data.get('headers', []),
                'rows': data.get('rows', [])
            }
        }
        
        return self.generate_pdf(report_data)
    
    def save_pdf(self, buffer, filename, save_path=None):
        """
        Save PDF to file
        
        Args:
            buffer: BytesIO object containing PDF data
            filename: Output filename
            save_path: Path to save the PDF (optional)
        """
        if not save_path:
            save_path = os.path.join(settings.MEDIA_ROOT, 'reports', 'pdf')
        
        os.makedirs(save_path, exist_ok=True)
        
        full_path = os.path.join(save_path, filename)
        
        with open(full_path, 'wb') as f:
            f.write(buffer.getvalue())
        
        return full_path


# Convenience functions
def generate_attendance_report(data, filename=None):
    """
    Convenience function to generate attendance report
    
    Args:
        data: Attendance report data
        filename: Output filename (optional)
        
    Returns:
        BytesIO object containing the PDF
    """
    generator = PDFGenerator()
    buffer = generator.generate_attendance_report(data)
    
    if filename:
        generator.save_pdf(buffer, filename)
    
    return buffer


def generate_payment_report(data, filename=None):
    """
    Convenience function to generate payment report
    
    Args:
        data: Payment report data
        filename: Output filename (optional)
        
    Returns:
        BytesIO object containing the PDF
    """
    generator = PDFGenerator()
    buffer = generator.generate_payment_report(data)
    
    if filename:
        generator.save_pdf(buffer, filename)
    
    return buffer


def generate_settlement_report(data, filename=None):
    """
    Convenience function to generate settlement report
    
    Args:
        data: Settlement report data
        filename: Output filename (optional)
        
    Returns:
        BytesIO object containing the PDF
    """
    generator = PDFGenerator()
    buffer = generator.generate_settlement_report(data)
    
    if filename:
        generator.save_pdf(buffer, filename)
    
    return buffer
