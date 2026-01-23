from django.contrib import admin
from apps.students.models import Student
from apps.attendance.models import Attendance
from apps.payments.models import Payment


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['barcode', 'full_name', 'group', 'financial_status', 'parent_phone', 'is_active']
    list_filter = ['financial_status', 'is_active', 'group']
    search_fields = ['barcode', 'full_name', 'parent_phone']
    ordering = ['full_name']


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['student', 'session', 'scan_time', 'status']
    list_filter = ['status', 'scan_time']
    search_fields = ['student__full_name', 'student__barcode']
    ordering = ['-scan_time']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['student', 'month', 'amount_due', 'amount_paid', 'status', 'sessions_attended']
    list_filter = ['status', 'month']
    search_fields = ['student__full_name', 'student__barcode']
    ordering = ['-month']
