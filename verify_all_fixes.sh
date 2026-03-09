#!/bin/bash
# Comprehensive verification script for all bug fixes

echo "=========================================="
echo "  Codebase-Wide Bug Fixes Verification"
echo "=========================================="
echo ""

PASS=0
FAIL=0

check_file() {
    local file=$1
    local pattern=$2
    local description=$3
    
    if grep -q "$pattern" "$file" 2>/dev/null; then
        echo "✓ $description"
        ((PASS++))
    else
        echo "✗ $description"
        ((FAIL++))
    fi
}

echo "=== Phone Link Fixes ==="
echo ""

check_file "templates/teachers/bookings/search.html" 'href="tel:{{ teacher.phone }}"' \
    "Teachers Bookings - phone link"

check_file "templates/teachers/list.html" 'href="tel:{{ teacher.phone }}"' \
    "Teachers List - phone link"

check_file "templates/teachers/detail.html" 'href="tel:{{ teacher.phone }}"' \
    "Teacher Detail - phone link"

check_file "templates/students/detail.html" 'href="tel:{{ student.student_phone }}"' \
    "Student Detail - student phone link"

check_file "templates/students/detail.html" 'href="tel:{{ student.parent_phone }}"' \
    "Student Detail - parent phone link"

check_file "templates/notifications/contact_list.html" 'href="tel:{{ contact.parent_phone }}"' \
    "Notifications Contact List - phone link"

echo ""
echo "=== Appointments & Attendance Sections ==="
echo ""

check_file "templates/teachers/bookings/search.html" 'المواعيد و الحضور' \
    "Teachers Bookings - attendance section title"

check_file "templates/teachers/bookings/search.html" 'attendance_stats.present' \
    "Teachers Bookings - attendance stats display"

check_file "templates/teachers/bookings/search.html" 'upcoming_sessions' \
    "Teachers Bookings - upcoming sessions display"

check_file "templates/teachers/detail.html" 'المواعيد القادمة' \
    "Teacher Detail - upcoming sessions section"

check_file "templates/teachers/detail.html" 'for session in upcoming_sessions' \
    "Teacher Detail - upcoming sessions loop"

echo ""
echo "=== Backend Changes ==="
echo ""

check_file "apps/teachers/views.py" 'from apps.attendance.models import Session, Attendance' \
    "Views - attendance models imported"

check_file "apps/teachers/views.py" 'upcoming_sessions = Session.objects.filter' \
    "Views - upcoming sessions query (booking_search)"

check_file "apps/teachers/views.py" 'attendance_stats = Attendance.objects.filter' \
    "Views - attendance stats query"

check_file "apps/teachers/views.py" 'group__teacher=teacher' \
    "Views - teacher-specific sessions query (teacher_detail)"

echo ""
echo "=========================================="
echo "  Results: $PASS passed, $FAIL failed"
echo "=========================================="
echo ""

if [ $FAIL -eq 0 ]; then
    echo "✓ All fixes verified successfully!"
    echo ""
    echo "Next Steps:"
    echo "1. Restart Django server: python manage.py runserver"
    echo "2. Test each page manually"
    echo "3. Verify phone links open dialer"
    echo "4. Verify attendance sections display data"
    exit 0
else
    echo "✗ Some fixes are missing. Please review the output above."
    exit 1
fi
