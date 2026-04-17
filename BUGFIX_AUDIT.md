# BUGFIX AUDIT — Attendance Scanner & Sticker Printing

**Date**: 2026-04-17  
**Author**: Automated audit  
**Files reviewed**:
- `apps/attendance/services.py` (AttendanceService.process_scan)
- `apps/attendance/views.py` (process_student_code endpoint)
- `apps/attendance/api_views.py` (process_scan API)
- `apps/attendance/models.py` (Session, Attendance)
- `apps/students/views.py` (student_qr_ticket)
- `templates/students/qr_ticket.html` (sticker template)
- `templates/attendance/scanner.html` (scanner UI + JS)
- `apps/students/urls.py`
- `apps/attendance/urls.py`

---

## Bug 1: Repeat scan returns "فشل تسجيل الحضور" instead of friendly message

### Current behavior (code quote)

**`apps/attendance/services.py` lines 199–206:**
```python
# التحقق من عدم التسجيل المسبق
if Attendance.objects.filter(student=student, session=session).exists():
    return {
        'success': False,
        'message': 'تم تسجيل الحضور مسبقاً',
        'sound': 'error',
        'instant_status': instant_status,
    }
```

**`templates/attendance/scanner.html` — `displayResult()` function:**
```javascript
if (data.success) {
    resultCard.className = 'result-card success';
    resultTitle.textContent = 'تم تسجيل الحضور بنجاح';
} else {
    resultCard.className = 'result-card error';
    resultTitle.textContent = 'فشل تسجيل الحضور';
}
```

### Root cause
The service returns `success: False` when a duplicate attendance record is detected. The frontend treats ALL `success: False` as errors and shows "فشل تسجيل الحضور" with a red card and error sound.

### Fix
1. In `services.py`: use `get_or_create` instead of checking `.exists()` + `.create()`. Return `success: True` with `status: 'already_registered'` and the original scan time.
2. In `scanner.html`: add a third display branch for `already_registered` — show blue/info card, not red error.

### Risks
- None. The `Attendance` model has `unique_together = ['student', 'session']`, so `get_or_create` is safe and atomic.

---

## Bug 2: Student in two same-day groups → only one session registered

### Current behavior (code quote)

**`apps/attendance/services.py` lines 134–180 (session matching loop):**
```python
for enr in enrollments:
    group = enr.group
    # ... schedule matching ...
    if early_window <= current_time_local <= session_end:
        matching_group = group
        enrollment = enr
        matched_schedule = {'time': schedule_time, 'duration': duration}
        break  # ← STOPS AT FIRST MATCH
```

Then at line 199+ the code registers attendance for only `matching_group` (singular).

### Root cause
The loop uses `break` after finding the first matching group. If a student is enrolled in Group A (10:00 AM) and Group B (10:15 AM), and scans at 10:05, only Group A gets registered.

### Fix
1. Replace single-match loop with a collection loop that gathers ALL matching groups/schedules.
2. For each matching group: check time rules, check financial status, then register via `get_or_create`.
3. Return aggregated results (list of `newly_registered` + `already_registered`).

### Risks
- Must preserve per-group time validation (10-min rule) and per-group financial checks.
- Each group's instant_status and financial check is independent.
- If one group passes and another fails, report both outcomes. A partial success is still `success: True`.

---

## Bug 3: Thermal sticker re-print breaks

### Current behavior
- `apps/students/views.py:student_qr_ticket` renders `templates/students/qr_ticket.html` with `barcode_base64` from `student.get_barcode_base64()`.
- Template uses inline `data:image/png;base64,...` images.
- Browser `window.print()` with dynamic `@page` style injection.

### Root cause
Multiple browser-side issues:
1. Chrome caches the print preview state; re-printing without page reload can show stale DOM.
2. The `setPageSize()` function creates/removes `<style>` elements dynamically — race conditions with print dialog.
3. `data:` URIs for images may be decoded inconsistently across print calls.
4. No `Cache-Control` headers — the page itself may be served from browser cache with stale barcode data.

### Fix
Generate the sticker as a **server-side PDF** using ReportLab:
1. Create `apps/students/services/sticker_pdf.py` — builds a 35mm × 10mm PDF with barcode + name + code.
2. Add `qr_ticket_pdf` view in `apps/students/views.py` with `no-cache` headers.
3. Add URL `<int:student_id>/qr-ticket/pdf/` in `apps/students/urls.py`.
4. Update student detail template button to point to the PDF endpoint.
5. Keep old `qr_ticket` HTML route as fallback.

### Risks
- Need Cairo TTF fonts in `static/fonts/`. Will download from Google Fonts.
- ReportLab is already in `requirements.txt` (reportlab==4.0.9).
- Arabic text in ReportLab needs RTL shaping — but we only print the student name (short, no complex ligatures needed) and the code (digits). The code is LTR. Name is truncated to 10 chars.

---

## Summary of changes

| Bug | File(s) changed | Nature of change |
|-----|-----------------|------------------|
| 1 | `services.py`, `scanner.html` | `get_or_create` + info toast |
| 2 | `services.py`, `scanner.html` | Multi-session loop + aggregated results |
| 3 | New `sticker_pdf.py`, `views.py`, `urls.py`, `detail.html` | Server-side PDF sticker |
