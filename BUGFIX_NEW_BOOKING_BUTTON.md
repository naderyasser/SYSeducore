# Bug Fix: Incorrect Redirection on 'New Booking' Button
**Date**: 2026-02-10
**Location**: https://sys.educore.software/teachers/bookings/calendar/
**Status**: ✅ FIXED

---

## Issue

**Button**: "حجز موعد جديد" (New Booking)
**Current Behavior**: Redirects to `/teachers/bookings/` (search page)
**Expected Behavior**: Redirect to `/teachers/bookings/create/` (create form)

---

## Root Cause

The button's `href` attribute was pointing to the wrong URL:

**Before**:
```html
<a href="{% url 'teachers:booking_search' %}" class="btn-action btn-primary">
    <i class="bi bi-plus-circle"></i>
    حجز موعد جديد
</a>
```

**Issue**: Used `booking_search` instead of `booking_create`

---

## Fix Applied

**File**: `templates/teachers/bookings/calendar.html`

**After**:
```html
<a href="{% url 'teachers:booking_create' %}" class="btn-action btn-primary">
    <i class="bi bi-plus-circle"></i>
    حجز موعد جديد
</a>
```

**Change**: `booking_search` → `booking_create`

---

## URL Mapping

From `apps/teachers/urls.py`:
```python
path('bookings/create/', views.booking_create, name='booking_create'),
path('bookings/create/<int:teacher_id>/', views.booking_create, name='booking_create_for_teacher'),
```

---

## Testing

### Before Fix:
1. Go to: https://sys.educore.software/teachers/bookings/calendar/
2. Click "حجز موعد جديد"
3. ❌ Redirects to `/teachers/bookings/` (wrong page)

### After Fix:
1. Go to: https://sys.educore.software/teachers/bookings/calendar/
2. Click "حجز موعد جديد"
3. ✅ Redirects to `/teachers/bookings/create/` (correct page)

---

## Verification

```bash
grep -B2 "حجز موعد جديد" templates/teachers/bookings/calendar.html
```

**Output**:
```html
<a href="{% url 'teachers:booking_create' %}" class="btn-action btn-primary">
    <i class="bi bi-plus-circle"></i>
    حجز موعد جديد
```

✅ Confirmed: URL now points to `booking_create`

---

## Impact

- ✅ Users can now create new bookings from calendar page
- ✅ Button behavior matches user expectations
- ✅ Proper workflow: Calendar → Create Booking Form

---

## Status

✅ **FIXED** - Button now correctly redirects to booking creation form.
