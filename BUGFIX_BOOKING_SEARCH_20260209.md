# Bug Fix Report - Booking Search FieldError

**Date:** 2026-02-09 16:12 UTC  
**Issue:** FieldError at /teachers/bookings/  
**Status:** ✅ FIXED

## Problem

```
FieldError: Cannot resolve keyword 'education_stage' into field. 
Choices are: created_at, email, full_name, groups, hire_date, is_active, 
phone, photo, specialization, subjects, teacher_id, updated_at
```

The `booking_search` view was trying to filter Teacher model directly by:
- `education_stage` 
- `gender`

But these fields don't exist on the Teacher model - they exist on the Group model.

## Root Cause

The Teacher model has a many-to-one relationship with Group through `related_name='groups'`. The fields `education_stage` and `gender_type` are on the Group model, not Teacher.

## Solution

Changed the filter queries to use the relationship:

```python
# Before (WRONG):
if education_stage:
    teachers = teachers.filter(education_stage=education_stage)

if gender:
    teachers = teachers.filter(gender=gender)

# After (CORRECT):
if education_stage:
    teachers = teachers.filter(groups__education_stage=education_stage)

if gender:
    teachers = teachers.filter(groups__gender_type=gender)
```

## Changes Made

**File:** `apps/teachers/views.py`  
**Function:** `booking_search` (line 403-407)

- Line 403: `education_stage=education_stage` → `groups__education_stage=education_stage`
- Line 406: `gender=gender` → `groups__gender_type=gender`

## Deployment

1. ✅ Fixed code in `apps/teachers/views.py`
2. ✅ Reloaded gunicorn (graceful reload)
3. ✅ Committed to git: `3c4d8d9`
4. ✅ Pushed to GitHub (master branch)
5. ✅ Endpoint tested and working

## Testing

```bash
# Test URL that was failing:
https://sys.educore.software/teachers/bookings/?q=&education_stage=preparatory&gender=female&subject=

# Result: ✅ Working (no more FieldError)
```

## Impact

- Zero downtime fix
- No database changes required
- Backward compatible
- All other routes unaffected

---

**Commit:** `3c4d8d9 - Fix booking search: filter teachers through groups relationship`
