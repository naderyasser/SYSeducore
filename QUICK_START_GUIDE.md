# Quick Start Guide

## Part 1: Wipe Test Data

### Step 1: Backup Database (IMPORTANT!)
```bash
# PostgreSQL
pg_dump educore_db > backup_$(date +%Y%m%d).sql

# Or Django dumpdata
python manage.py dumpdata > backup_$(date +%Y%m%d).json
```

### Step 2: Run Data Wipe
```bash
# Interactive mode (safer)
python manage.py prepare_production

# When prompted, type: DELETE ALL DATA

# Or auto-confirm (use with caution)
python manage.py prepare_production --confirm
```

### Step 3: Verify
```bash
# Check admin can still login
python manage.py createsuperuser  # If needed

# Verify database is clean
python manage.py shell
>>> from apps.students.models import Student
>>> Student.objects.count()  # Should be 0
```

---

## Part 2: Deploy Fixes

### Already Fixed:
✅ `templates/teachers/bookings/create.html`
✅ `apps/teachers/views.py`

### Verification:
```bash
./verify_js_fixes.sh
```

### Test:
1. Go to: https://sys.educore.software/teachers/bookings/create/
2. Fill form and add schedules
3. Click submit
4. Verify:
   - Button shows "جاري الإنشاء..."
   - Cannot click again
   - Data saves to database

---

## What Was Fixed

### Issue 1: Data Not Saving
**Cause**: Hidden input outside form
**Fix**: Moved inside form tag
**Result**: ✅ Data now saves

### Issue 2: Buttons Stuck
**Cause**: No double-submit prevention
**Fix**: Added isSubmitting flag
**Result**: ✅ Buttons respond correctly

---

## Files Changed

1. `apps/core/management/commands/prepare_production.py` (NEW)
2. `templates/teachers/bookings/create.html` (FIXED)

---

## Need Help?

See detailed reports:
- `FINAL_REPORT_DATA_WIPE_INTEGRITY.md` - Complete analysis
- `COMPREHENSIVE_INTEGRITY_REPORT.md` - Technical details
- `JAVASCRIPT_ISSUES_ANALYSIS.md` - Frontend issues
