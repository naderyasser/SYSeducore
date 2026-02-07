#!/usr/bin/env python
"""
Quick test to verify JSON serialization fix for attendance API
"""
import os
import sys
import django
import json

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import RequestFactory
from apps.attendance.views import process_student_code
from apps.accounts.models import User
from apps.students.models import Student
from apps.teachers.models import Group, Room
from apps.students.models import StudentGroupEnrollment
from django.utils import timezone

# Create test data
print("Setting up test data...")

# Create a teacher user (supervisor)
supervisor, _ = User.objects.get_or_create(
    username='test_supervisor',
    defaults={'is_staff': True}
)

# Create or get a room
room, _ = Room.objects.get_or_create(
    room_id=1,
    defaults={'room_name': 'Room 1', 'capacity': 30}
)

# Create or get a group
group, _ = Group.objects.get_or_create(
    group_id=1,
    defaults={
        'group_name': 'Test Group',
        'subject': None,
        'teacher': None,
        'room': room,
        'schedule_day': 'Monday',
        'schedule_time': '10:00:00',
        'duration_minutes': 120
    }
)

# Create or get a student with a code
student, _ = Student.objects.get_or_create(
    student_code='TEST001',
    defaults={
        'full_name': 'Test Student',
        'student_phone': '+201001234567',
        'parent_phone': '+201001234567',
        'is_active': True
    }
)

# Enroll the student in the group
StudentGroupEnrollment.objects.get_or_create(
    student=student,
    group=group,
    is_active=True,
)

print(f"Test data created: Student '{student.full_name}' with code '{student.student_code}'")

# Test the endpoint
print("\nTesting process_student_code() endpoint...")
factory = RequestFactory()

# Create a POST request with student code
request = factory.post(
    '/attendance/api/process-code/',
    data=json.dumps({'student_code': 'TEST001'}),
    content_type='application/json'
)
request.user = supervisor

try:
    response = process_student_code(request)
    response_data = json.loads(response.content.decode('utf-8'))
    
    print(f"\nResponse Status: {response.status_code}")
    print(f"Response JSON (serializable): ✓ Success!")
    print(f"\nResponse Data:")
    print(json.dumps(response_data, indent=2, ensure_ascii=False))
    
    # Verify all data is JSON serializable
    if response_data.get('success'):
        print("\n✓ Test PASSED - JSON serialization is working correctly!")
    else:
        print(f"\n⚠ Warning: Response shows error: {response_data.get('message')}")
        
except Exception as e:
    print(f"\n✗ Test FAILED - JSON Serialization Error: {str(e)}")
    import traceback
    traceback.print_exc()

print("\nTest completed!")
