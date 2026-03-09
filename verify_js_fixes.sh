#!/bin/bash
# Verification script for JavaScript fixes

echo "=========================================="
echo "  JavaScript Fixes Verification"
echo "=========================================="
echo ""

PASS=0
FAIL=0

check() {
    if [ $? -eq 0 ]; then
        echo "✓ $1"
        ((PASS++))
    else
        echo "✗ $1"
        ((FAIL++))
    fi
}

FILE="templates/teachers/bookings/create.html"

echo "=== Critical Fixes ==="
echo ""

# Check 1: Hidden input inside form
grep -B5 '</form>' "$FILE" | grep -q 'id="schedulesInput"'
check "Hidden input is inside form tag"

# Check 2: No inline onclick on add button
! grep -q 'onclick="addSchedule()"' "$FILE"
check "Removed inline onclick from add schedule button"

# Check 3: Add schedule button has ID
grep -q 'id="addScheduleBtn"' "$FILE"
check "Add schedule button has ID"

# Check 4: Submit button has ID
grep -q 'id="submitBtn"' "$FILE"
check "Submit button has ID"

# Check 5: isSubmitting flag exists
grep -q 'let isSubmitting = false' "$FILE"
check "Double-submit prevention flag exists"

# Check 6: DOMContentLoaded wrapper
grep -q "document.addEventListener('DOMContentLoaded'" "$FILE"
check "Code wrapped in DOMContentLoaded"

# Check 7: Event listener for add button
grep -q "addScheduleBtn.addEventListener('click', addSchedule)" "$FILE"
check "Add schedule button uses addEventListener"

# Check 8: Null checks in updateSchedulesList
grep -A2 'function updateSchedulesList' "$FILE" | grep -q 'if (!container) return'
check "Null check in updateSchedulesList"

# Check 9: Button disable on submit
grep -q 'submitBtn.disabled = true' "$FILE"
check "Submit button disabled on submit"

# Check 10: Loading state on submit
grep -q 'جاري الإنشاء' "$FILE"
check "Loading state text exists"

# Check 11: No inline onclick in dynamic content
! grep -q 'onclick="removeSchedule(' "$FILE"
check "Removed inline onclick from dynamic buttons"

# Check 12: Data attributes for dynamic buttons
grep -q 'data-index=' "$FILE"
check "Using data attributes for dynamic content"

echo ""
echo "=========================================="
echo "  Results: $PASS passed, $FAIL failed"
echo "=========================================="
echo ""

if [ $FAIL -eq 0 ]; then
    echo "✓ All JavaScript fixes verified!"
    echo ""
    echo "The following issues have been fixed:"
    echo "  1. Hidden input now inside form (data transmission)"
    echo "  2. Double-submit prevention (button responsiveness)"
    echo "  3. Proper event listeners (no memory leaks)"
    echo "  4. Null checks (no crashes)"
    echo "  5. Loading states (better UX)"
    echo ""
    echo "Next: Test the page manually at:"
    echo "https://sys.educore.software/teachers/bookings/create/"
    exit 0
else
    echo "✗ Some fixes are missing!"
    exit 1
fi
