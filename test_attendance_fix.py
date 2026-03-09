"""
Test script to verify the attendance validation fix
"""
import os
import django
from datetime import time, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.models import Teacher, Group
from apps.attendance.services import AttendanceService
from django.contrib.auth import get_user_model

User = get_user_model()

def test_attendance_time_window():
    """Test that attendance validation respects time windows"""
    
    print("\n=== Testing Attendance Time Window Fix ===\n")
    
    # Create test data
    teacher = Teacher.objects.first()
    if not teacher:
        print("❌ No teacher found. Please create test data first.")
        return
    
    student = Student.objects.first()
    if not student:
        print("❌ No student found. Please create test data first.")
        return
    
    # Get current day
    current_day = AttendanceService.get_current_day_name()
    print(f"Current day: {current_day}")
    
    # Find or create a group for today
    group = Group.objects.filter(
        schedule_day=current_day,
        is_active=True
    ).first()
    
    if not group:
        print(f"❌ No active group found for {current_day}")
        return
    
    print(f"Testing with group: {group.group_name}")
    print(f"Schedule: {group.schedule_day} at {group.schedule_time}")
    print(f"Duration: {group.duration_minutes} minutes")
    
    # Ensure student is enrolled
    enrollment, created = StudentGroupEnrollment.objects.get_or_create(
        student=student,
        group=group,
        defaults={'is_active': True, 'financial_status': 'exempt'}
    )
    if created:
        print(f"✓ Enrolled student in group")
    
    # Get supervisor
    supervisor = User.objects.filter(is_staff=True).first()
    if not supervisor:
        print("❌ No supervisor found")
        return
    
    # Test scenarios
    current_time = timezone.now()
    session_start = timezone.make_aware(
        timezone.datetime.combine(current_time.date(), group.schedule_time)
    )
    session_end = session_start + timedelta(minutes=group.duration_minutes)
    
    print(f"\nSession window: {session_start.strftime('%I:%M %p')} - {session_end.strftime('%I:%M %p')}")
    print(f"Current time: {current_time.strftime('%I:%M %p')}")
    
    # Check if we're in the valid window
    early_window = session_start - timedelta(minutes=30)
    
    if early_window <= current_time <= session_end:
        print("\n✓ Current time is WITHIN the valid attendance window")
        print("  Expected: Attendance should be ACCEPTED")
        
        result = AttendanceService.process_scan(
            student_code=student.student_code,
            supervisor=supervisor
        )
        
        if result['success']:
            print(f"✅ TEST PASSED: {result['message']}")
        else:
            print(f"❌ TEST FAILED: {result['message']}")
            print("   This indicates the bug is NOT fixed")
    else:
        print("\n✓ Current time is OUTSIDE the valid attendance window")
        print("  Expected: Attendance should be REJECTED")
        
        result = AttendanceService.process_scan(
            student_code=student.student_code,
            supervisor=supervisor
        )
        
        if not result['success']:
            print(f"✅ TEST PASSED: Correctly rejected - {result['message']}")
        else:
            print(f"❌ TEST FAILED: Should have been rejected but was accepted")
    
    print("\n=== Test Complete ===\n")

if __name__ == '__main__':
    test_attendance_time_window()
