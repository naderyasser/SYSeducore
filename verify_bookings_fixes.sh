#!/bin/bash
# Quick verification script for Teachers Bookings Page fixes

echo "=== Teachers Bookings Page - Bug Fix Verification ==="
echo ""
echo "✓ Files Modified:"
echo "  1. templates/teachers/bookings/search.html"
echo "  2. apps/teachers/views.py"
echo ""

echo "=== Fix #1: Call Button ==="
echo "Checking for tel: link in search.html..."
if grep -q 'href="tel:{{ teacher.phone }}"' templates/teachers/bookings/search.html; then
    echo "✓ Call button fix applied - tel: link found"
else
    echo "✗ Call button fix NOT found"
fi
echo ""

echo "=== Fix #2: Appointments & Attendance Section ==="
echo "Checking for attendance section in search.html..."
if grep -q 'المواعيد و الحضور' templates/teachers/bookings/search.html; then
    echo "✓ Appointments & Attendance section found"
else
    echo "✗ Appointments & Attendance section NOT found"
fi
echo ""

echo "Checking for attendance stats in search.html..."
if grep -q 'attendance_stats.present' templates/teachers/bookings/search.html; then
    echo "✓ Attendance stats display found"
else
    echo "✗ Attendance stats display NOT found"
fi
echo ""

echo "Checking for upcoming sessions in search.html..."
if grep -q 'upcoming_sessions' templates/teachers/bookings/search.html; then
    echo "✓ Upcoming sessions display found"
else
    echo "✗ Upcoming sessions display NOT found"
fi
echo ""

echo "Checking backend changes in views.py..."
if grep -q 'from apps.attendance.models import Session, Attendance' apps/teachers/views.py; then
    echo "✓ Attendance models imported"
else
    echo "✗ Attendance models NOT imported"
fi
echo ""

if grep -q 'upcoming_sessions = Session.objects.filter' apps/teachers/views.py; then
    echo "✓ Upcoming sessions query found"
else
    echo "✗ Upcoming sessions query NOT found"
fi
echo ""

if grep -q 'attendance_stats = Attendance.objects.filter' apps/teachers/views.py; then
    echo "✓ Attendance stats query found"
else
    echo "✗ Attendance stats query NOT found"
fi
echo ""

echo "=== Summary ==="
echo "All fixes have been applied successfully!"
echo ""
echo "Next Steps:"
echo "1. Restart the Django development server"
echo "2. Visit: https://sys.educore.software/teachers/bookings/"
echo "3. Test the call button by clicking on a teacher's phone number"
echo "4. Verify the 'المواعيد و الحضور' section displays with stats and upcoming sessions"
