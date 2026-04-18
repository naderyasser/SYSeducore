# SYSeducore Audit Report — 2026-04-17

## Executive Summary

- **Overall health score: 7/10**
- **Critical issues: 2**
- **High priority: 5**
- **Medium: 8**
- **Low: 10**
- **Production readiness: Yellow** — system is functional and serving users, but has security gaps, missing rate limiting, and timezone bugs that will bite under specific conditions.

---

## Critical Issues (fix immediately)

### CRIT-1: `get_current_day_name()` uses UTC weekday — wrong day near midnight

**File:** `apps/attendance/services.py:350`

```python
today = timezone.now().weekday()
```

`timezone.now()` returns UTC. Between 00:00–02:00 Cairo time (22:00–00:00 UTC), the weekday is **one day behind**. A student scanning at 00:30 Saturday Cairo time gets Friday's weekday. All schedule matching fails silently — students are told "no session now" when there IS a session.

**Impact:** Complete attendance failure for ~2 hours every night. This affects any center operating evening sessions.

**Fix:** Convert to local time first: `timezone.now().astimezone(pytz.timezone(settings.TIME_ZONE)).weekday()`

---

### CRIT-2: No rate limiting on scan endpoint — brute-force exposure

**File:** `apps/attendance/views.py:24` (`process_student_code`)

`django-ratelimit` is installed (`requirements.txt:20`) and `RATELIMIT_ENABLE=True` (`settings.py:299`), but **no `@ratelimit` decorator** is applied to the scan endpoint. An attacker can:
- Enumerate all valid student codes by brute-forcing 4-digit codes (10,000 attempts)
- Flood the endpoint causing DB load

**Impact:** Information disclosure (student names/codes) and potential DoS.

**Fix:** Add `@ratelimit(key='ip', rate='30/m', method='POST', block=True)` to `process_student_code`.

---

## High Priority (fix this sprint)

### HIGH-1: `ENABLE_FIRST_MONTH_STRICT_PAYMENT` setting is dead code

**File:** `config/settings.py:277` (defined), `apps/attendance/services.py:477` (never read)

The setting exists in `.env` config but is never imported or checked. First-month strict payment is **always enforced** regardless of the flag. If the client tries to disable it, nothing happens.

**Fix:** Import `settings.ENABLE_FIRST_MONTH_STRICT_PAYMENT` in `check_financial_status` and gate the logic.

---

### HIGH-2: Subscription expiry uses UTC date, not Cairo date

**File:** `apps/students/models.py:302-304`

```python
return timezone.now().date() <= self.subscription_expiry_date
```

`.date()` extracts UTC date. Between midnight and ~2 AM Cairo time, students get an extra 2 hours of access beyond their subscription expiry date. Combined with CRIT-1, the midnight window has two simultaneous timezone bugs.

**Fix:** Use `timezone.localdate()` (Django built-in, respects `TIME_ZONE` setting).

---

### HIGH-3: `select_for_update()` is a no-op on SQLite — duplicate student codes possible

**File:** `apps/students/models.py:207-220`

`generate_next_code()` uses `select_for_update()` to prevent race conditions, but SQLite doesn't support row-level locking. Two concurrent student creation requests can generate the same code. The `unique` constraint on `student_code` will catch it at `save()` time, causing a 500 error instead of graceful retry.

**Impact:** Low probability in production (single admin usually creating students), but the error would be cryptic.

---

### HIGH-4: No log rotation configured — logs will grow unbounded

**Files:** `logs/access.log` (2.1 MB), `logs/django.log` (744 KB), `logs/error.log` (1.1 MB)

No logrotate configuration exists (`/etc/logrotate.d/syseducore` not found). With current traffic these are small, but `access.log` will grow ~60 MB/year. A high-traffic day (parent meetings, registration periods) could spike this. The `logging` config in `settings.py:302-325` uses `logging.FileHandler` (no rotation) instead of `RotatingFileHandler`.

---

### HIGH-5: `|safe` filter in templates — potential XSS via admin-injected data

**Files:**
- `templates/reports/financial.html:260` — `{{ monthly_data|safe }}`
- `templates/reports/dashboard.html:862` — `{{ week_attendance_json|safe }}`

These render JSON data unescaped into `<script>` tags. If any data field (e.g., group name) contains a `</script>` injection, it breaks out of the script block. The data is admin-generated (low risk), but the pattern is unsafe.

**Fix:** Use `{{ data|json_script:"id" }}` (Django 2.1+) instead of `|safe` in script blocks.

---

## Medium Priority (fix this quarter)

### MED-1: No file upload size/type validation on teacher photos

**File:** `apps/teachers/models.py:91-92`

```python
photo = models.ImageField(upload_to='teachers/photos/')
```

No `validators` for file size or content type. A malicious user could upload a 500 MB file or a file with a `.jpg` extension but executable content. Django's `ImageField` validates it's a valid image via Pillow, but doesn't enforce size limits.

**Fix:** Add `MaxFileSizeValidator` or check in the form's `clean_photo()` method.

---

### MED-2: Midnight-crossing sessions break room overlap detection

**File:** `apps/teachers/models.py:252-254`

```python
datetime.combine(datetime.today(), self.schedule_time) + timedelta(minutes=self.duration_minutes)
```

If a session starts at 23:00 with 120-minute duration, `get_end_time()` returns `01:00`. The overlap comparison `new_start < other_end` sees `01:00 < 23:00` = False, missing the overlap. Unlikely in education (late-night sessions), but the logic is mathematically wrong.

---

### MED-3: `float` ↔ `Decimal` round-trips in financial calculations

**File:** `apps/payments/services.py:30, 36-37, 100-101`

Financial values are converted `Decimal → float` for JSON responses, then back to `Decimal` in downstream calculations. Floating-point arithmetic introduces rounding errors in money calculations.

**Fix:** Use `str(decimal_value)` in JSON serialization, or Django's `DjangoJSONEncoder` which handles `Decimal` natively.

---

### MED-4: Soft-deleted teacher's groups remain active

**File:** `apps/teachers/views.py:155-156`

When a teacher is soft-deleted, their groups (and all enrolled students) remain fully active and visible. The scanner, enrollment, and payment systems continue to reference the "deleted" teacher. This creates an inconsistent state visible to users.

**Fix:** Cascade soft-delete to groups, or prevent soft-deleting teachers with active groups.

---

### MED-5: 60 unused imports across codebase

**Source:** pyflakes analysis (`/tmp/pyflakes.txt`)

Major offenders:
- `apps/reports/views.py` — 9 unused imports (`Avg`, `F`, `TruncDate`, `TruncMonth`, `defaultdict`, etc.)
- `apps/students/views.py` — 6 unused imports (`Exists`, `OuterRef`, `StudentQuickForm`, `Case`, `When`)
- `apps/teachers/views.py` — 3 unused imports
- `apps/attendance/views.py` — 5 unused imports

These increase load time and create confusion about what's actually used.

---

### MED-6: Hardcoded `/static/` in lockout middleware

**File:** `apps/accounts/middleware.py:20`

```python
request.path.startswith('/static/')
```

Should use `settings.STATIC_URL` instead of hardcoded string.

---

### MED-7: Sticker PDF silently falls back to Helvetica for Arabic

**File:** `apps/students/services/sticker_pdf.py:22-38`

If neither Cairo nor DejaVuSans fonts are found, the Arabic student name renders as empty boxes (Helvetica has no Arabic glyphs). No warning or error is logged. The fonts exist currently (`static/fonts/DejaVuSans.ttf`), but if they're accidentally deleted during a deploy, stickers silently break.

---

### MED-8: `get_instant_status` loads all Payment objects into Python memory

**File:** `apps/attendance/services.py:48-51`

```python
sum((p.amount_due - p.amount_paid) for p in arrears)
```

This materializes the entire queryset. Should use `.aggregate(total=Sum(F('amount_due') - F('amount_paid')))` for DB-level calculation. Currently low impact (few payments per student), but doesn't scale.

---

## Low Priority / Tech Debt

### LOW-1: 19 dead code locations detected by vulture

**Source:** `/tmp/vulture.txt`

Notable: `apps/accounts/decorators.py:2` unused `PermissionDenied`, `apps/accounts/forms.py:3` unused `SetPasswordForm`, `apps/students/api_views.py:9` unused `csrf_exempt`.

### LOW-2: Multiple `timezone.now()` calls in single `process_scan` invocation

**File:** `apps/attendance/services.py` — called at lines ~102, 141, 233, 462, 525

The date could theoretically roll over between calls at midnight. Should capture `now` once at method entry.

### LOW-3: Duplicate overlap detection logic

**File:** `apps/teachers/models.py:262-290` and `apps/teachers/models.py:397-420`

Room overlap check is copy-pasted between `Group.clean()` and `GroupSchedule.clean()`. Should be extracted to a shared utility.

### LOW-4: `datetime.today()` used instead of `timezone.now()`

**File:** `apps/teachers/models.py:252, 266, 393, 406`

Used only for `.time()` extraction so functionally harmless, but inconsistent with codebase conventions.

### LOW-5: No backup strategy documented or automated

The only backups are two manual snapshots from February 2026:
- `db.sqlite3.backup_before_cleanup_20260209_110214`
- `db.sqlite3.backup_final_20260209_133331`

No cron job, no off-site backup, no point-in-time recovery. SQLite is a single file — disk failure = total data loss.

### LOW-6: `SESSION_COOKIE_SAMESITE` defaults to `Lax`

**File:** `config/settings.py` (not explicitly set, Django default)

`Lax` is fine for most cases but `Strict` would be more secure for a management system that never needs cross-site form submissions.

### LOW-7: Celery worker not running in production

`ps aux | grep celery` returns empty. The `CELERY_BEAT_SCHEDULE` defines two tasks (attendance notifications every 5 min, monthly reminders) but no Celery worker is active. WhatsApp notifications and scheduled tasks are silently not executing.

### LOW-8: `reset_db_keep_superadmin` management command has SQL injection pattern

**File:** `apps/accounts/management/commands/reset_db_keep_superadmin.py:31,35`

Bandit flagged string-based SQL construction. This is a management command (admin-only), not a web endpoint, so the risk is minimal. But the pattern should be cleaned up.

### LOW-9: Teacher detail page never renders the actual photo

**File:** `templates/teachers/detail.html:16-17`

Always shows a generic icon regardless of whether `teacher.photo` exists.

### LOW-10: 81 stale Django sessions in DB

81 session records exist. With `SESSION_ENGINE = 'django.contrib.sessions.backends.db'` and 1-hour timeout, expired sessions accumulate. `manage.py clearsessions` should be scheduled.

---

## Positive Findings

1. **341/341 tests pass** in 7.6 seconds — strong test coverage across all apps including unit, functional, integration, permissions, and financial tests.

2. **Zero Django deploy warnings** — `manage.py check --deploy` passes clean.

3. **No missing migrations** — `makemigrations --check` confirms model/migration parity.

4. **Security settings properly gated** — `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT`, `HSTS` all enabled when `DEBUG=False`. SECRET_KEY loaded from `.env`.

5. **SSL certificate valid** — expires June 22, 2026 (66 days remaining). Adequate buffer.

6. **Gunicorn properly configured** — 4 gthread workers, 2 threads each, max-requests=1000 with jitter (prevents memory leaks). Memory: ~110-147 MB per worker, reasonable.

7. **Systemd service healthy** — running 7+ hours, no restarts, 428 MB total memory.

8. **Disk space adequate** — 180 GB free (46% used). DB is only 624 KB.

9. **Soft delete + activity logging** implemented consistently — no permanent deletions, every action tracked with user/IP.

10. **RBAC with 3 roles** (admin/supervisor/teacher) — 100 `@login_required`/`@admin_required` decorators across views. Auth coverage is thorough.

11. **Concurrent scan race condition handled** — `unique_together = ['student', 'session']` + `get_or_create` in `process_scan` correctly handles simultaneous scans.

12. **Multi-session attendance** — recently fixed to register a student in multiple same-day groups with a single scan. Per-group time and financial checks are independent.

13. **Server-side PDF sticker generation** — eliminates browser print caching issues. Correct dimensions (35mm × 10mm) with Arabic support.

---

## Detailed Findings by Phase

### Phase 1: Test Suite

| Metric | Value |
|--------|-------|
| Total tests | 341 |
| Pass | 341 |
| Fail | 0 |
| Error | 0 |
| Skipped | 0 |
| Duration | 7.650s |

**Coverage by app:**
- `attendance` — 35 tests (services, views, models, strict time, financial blocking, subscriptions)
- `students` — 27 tests (model, views, forms, enrollment)
- `teachers` — 9 tests (room, group conflicts)
- `payments` — 9 tests (model, settlement)
- `notifications` — 16 tests (WhatsApp service, timing)
- `accounts` — tests via permissions and auth tests
- Cross-cutting — 83 tests (structure, permissions, financials, functional, comprehensive)

**Gaps:** No tests for `sticker_pdf.py`, `api_views.py` endpoints, `context_processors.py`, or the `reset_db_keep_superadmin` management command.

### Phase 2: Code Quality

- **Django deploy checks:** 0 issues (0 silenced)
- **Missing migrations:** None
- **Dead code (vulture):** 19 findings at 80%+ confidence
- **Unused imports (pyflakes):** 60 findings across 20 files
- **Worst offenders:** `apps/reports/views.py` (9 unused), `apps/students/views.py` (6 unused), `apps/attendance/views.py` (5 unused)

### Phase 3: Security Audit

**Bandit results:** 34 total issues (0 High, 2 Medium, 32 Low)
- 2× Medium: SQL construction in management command (admin-only, low risk)
- 23× Low: `random.choice()` for student code generation (not security-sensitive)
- 5× Low: Hardcoded `testpass123` in test files (expected)
- 3× Low: `try/except/pass` patterns
- 1× Low: `try/except/continue` pattern

**Manual security review:**
| Check | Status |
|-------|--------|
| `DEBUG` in production | ✅ `False` (from `.env`) |
| `SECRET_KEY` handling | ✅ From `.env`, insecure default only for dev |
| `ALLOWED_HOSTS` | ✅ `localhost, 127.0.0.1, sys.educore.software` |
| CSRF settings | ✅ `CSRF_TRUSTED_ORIGINS` properly set |
| Session cookies | ✅ `Secure=True, HttpOnly=True, SameSite=Lax` |
| SQL injection (`.raw()`, `.extra()`) | ✅ None found in app code |
| XSS (`\|safe`, `mark_safe`) | ⚠️ 2 uses in report templates (see HIGH-5) |
| File upload validation | ⚠️ No size limits (see MED-1) |
| Auth decorators | ✅ 100 decorators across views |
| Password storage | ✅ Django default PBKDF2 |
| Rate limiting | ❌ Installed but not applied (see CRIT-2) |
| Admin path | ✅ Default `/admin/` — consider renaming |

### Phase 4: Database Health

| Table | Records | Notes |
|-------|---------|-------|
| `students.Student` | 284 | 17 soft-deleted |
| `students.StudentGroupEnrollment` | 307 | |
| `teachers.Teacher` | 26 | 1 soft-deleted |
| `teachers.Group` | 79 | 3 soft-deleted |
| `teachers.GroupSchedule` | 137 | |
| `teachers.Room` | 9 | |
| `teachers.Subject` | 8 | |
| `attendance.Session` | 56 | |
| `attendance.Attendance` | 3 | Very low — suggests system is new or was reset |
| `attendance.ActivityLog` | 526 | Growing unbounded |
| `payments.Payment` | 3 | |
| `notifications.WhatsAppMessage` | 2 | |
| `sessions.Session` (Django) | 81 | Needs cleanup |
| `accounts.User` | 4 | |
| **DB size** | **624 KB** | Tiny — no immediate concern |

**Observations:**
- Only 3 attendance records vs 284 students suggests the system was recently reset or is in early use
- 526 activity logs will grow linearly — no pruning mechanism
- 81 Django sessions should be cleaned (`manage.py clearsessions`)
- No orphaned records detected (FK constraints are `PROTECT`)

### Phase 5: Smoke Tests

Covered in bug fix verification from previous session:
- ✅ Student scan (registered) — works
- ✅ Repeat scan (already_registered with `success=True`) — works
- ✅ Multi-session registration — works (2 groups, 1 scan)
- ✅ PDF sticker generation — 47,149 bytes, valid
- ⚠️ Expired subscription → correctly blocked
- ⚠️ Financial block → correctly enforced

### Phase 6: Performance

**N+1 Query Hotspots (top 5):**

| Location | Issue |
|----------|-------|
| `apps/attendance/views.py:183-198` | Session loop with per-session `attendees_count` query |
| `apps/attendance/views.py:129-152` | Dashboard: 4 separate count queries (could be 1 aggregate) |
| `apps/notifications/views.py:36-44` | WhatsApp dashboard: 4 separate count queries |
| `apps/accounts/views.py:60` | `User.objects.all()` without `select_related` |
| `apps/attendance/views.py:244` | Attendance export without `select_related('student', 'session')` |

**Resource usage:**
| Resource | Size |
|----------|------|
| Static files | 2.2 MB |
| Media files | 1.9 MB (barcodes: 1.4 MB) |
| `access.log` | 2.1 MB |
| `django.log` | 744 KB |
| `error.log` | 1.1 MB |
| Gunicorn master | 24 MB |
| Gunicorn workers (×4) | 110-147 MB each |
| Total app memory | ~428 MB |

**No Celery workers running** — scheduled tasks (WhatsApp notifications, monthly reminders) are not executing.

### Phase 7: Dependencies & Infrastructure

| Component | Version | Status |
|-----------|---------|--------|
| Python | 3.13.5 | ✅ Current |
| Django | 5.0.1 | ⚠️ 5.0.x is in standard support but 5.1/5.2 available |
| Gunicorn | 21.2.0 | ✅ Stable |
| Nginx | — | ✅ Config valid (deprecated `http2` directive warnings) |
| SSL cert | Expires 2026-06-22 | ✅ 66 days remaining |
| Disk | 180 GB free (46%) | ✅ Adequate |
| Systemd | Active 7h, no restarts | ✅ Stable |
| Logrotate | Not configured | ❌ See HIGH-4 |
| Backups | Manual snapshots only | ⚠️ See LOW-5 |
| Celery | Not running | ❌ See LOW-7 |

### Phase 8: Manual Code Review

See subagent findings integrated into Critical/High/Medium sections above. Key summary:

| File | Lines | Complexity | Issues |
|------|-------|-----------|--------|
| `attendance/services.py` | ~550 | High | UTC day name (CRIT-1), multiple `timezone.now()` calls (LOW-2) |
| `students/models.py` | ~400 | Medium | `select_for_update` no-op (HIGH-3), UTC date (HIGH-2) |
| `sticker_pdf.py` | ~70 | Low | Silent font fallback (MED-7), magic numbers |
| `teachers/models.py` | ~420 | Medium | Midnight overlap bug (MED-2), duplicate logic (LOW-3) |
| `payments/services.py` | ~110 | Low | float/Decimal mixing (MED-3) |
| `accounts/middleware.py` | ~50 | Low | Hardcoded path (MED-6), double session flush |

### Phase 9: UX & Frontend Review

| Check | Count | Status |
|-------|-------|--------|
| `dir="rtl"` tags | 8 | ✅ Present in key templates |
| LTR leaks (`text-align: left`) | 4 | ⚠️ In scanner, room detail, bookings |
| Viewport meta tags | 5 templates | ✅ `base.html`, `login.html`, etc. |
| Inline `<script>` tags | 25 | ⚠️ High — should be extracted to `.js` files |
| Inline `<style>` tags | 37 | ⚠️ High — should be extracted to `.css` files |
| `\|safe` filter | 2 uses | ⚠️ See HIGH-5 |
| Images without `alt` | 2 | ⚠️ `students/list.html:739, 953` |
| Form fields without labels | 10+ | ⚠️ Report filter forms lack `<label>` elements |

**LTR leak details:**
- `templates/teachers/rooms/detail.html:216` — `text-align: left` on room capacity
- `templates/teachers/bookings/search.html:450` — booking search button
- `templates/attendance/scanner.html:423,523` — barcode display (intentional for LTR codes)

### Phase 10: Business Logic Edge Cases

| # | Edge Case | Status | Details |
|---|-----------|--------|---------|
| 1 | 10-min late rule at exact boundary | ✅ | `> 10` = inclusive at 10 min (`services.py:405`) |
| 2 | Multi-session per-group late check | ✅ | Independent time check per group (`services.py:152-199`) |
| 3 | Subscription expiry at midnight | ⚠️ | UTC `.date()` gives ~2 extra hours (HIGH-2) |
| 4 | `ENABLE_FIRST_MONTH_STRICT_PAYMENT` | ❌ | Setting defined but never read (HIGH-1) |
| 5 | Teacher photo missing from disk | ⚠️ | Template checks DB field, not file existence |
| 6 | Deleted teacher → groups | ⚠️ | Groups stay active with soft-deleted teacher (MED-4) |
| 7 | Group rescheduled → old sessions | ⚠️ | Past sessions untouched (by design, acceptable) |
| 8 | Rapid repeat scans | ❌ | No rate limiting (CRIT-2) |
| 9 | Concurrent scans | ✅ | `unique_together` + `get_or_create` handles it |
| 10 | Timezone in day name | ❌ | UTC weekday used (CRIT-1) |

---

## Recommendations (prioritized)

1. **Fix `get_current_day_name()` timezone** — CRIT-1, one-line fix, prevents 2-hour nightly outage
2. **Add `@ratelimit` to scan endpoint** — CRIT-2, one-line decorator, prevents brute-force
3. **Wire `ENABLE_FIRST_MONTH_STRICT_PAYMENT` setting** — HIGH-1, client-facing config that's currently dead
4. **Use `timezone.localdate()` for subscription check** — HIGH-2, one-line fix
5. **Add logrotate config** — HIGH-4, create `/etc/logrotate.d/syseducore`, 5 minutes
6. **Replace `|safe` with `json_script`** — HIGH-5, prevents XSS in report pages
7. **Start Celery worker** or document it's intentionally disabled — LOW-7, WhatsApp notifications are broken
8. **Set up automated DB backup** — LOW-5, `sqlite3 db.sqlite3 ".backup /backup/syseducore_$(date +%Y%m%d).db"` in cron
9. **Clean up unused imports** — MED-5, improves code clarity
10. **Add file upload size validation** — MED-1, add `MaxValueValidator` to teacher photo form

---

## Appendix

### Tool Versions Used
- vulture 2.14 (dead code detection)
- pyflakes 3.2 (unused imports)
- bandit 1.9.4 (security scanner)

### Raw Output Locations
- Test output: `/tmp/test_output.txt`
- Deploy checks: `/tmp/deploy_check.txt`
- Migrations check: `/tmp/migrations_check.txt`
- Vulture: `/tmp/vulture.txt` (19 findings)
- Pyflakes: `/tmp/pyflakes.txt` (60 findings)
- Bandit: `/tmp/bandit.txt` (34 findings)

### Audit Methodology
- All phases ran against the production database and live server
- No code was modified during this audit
- Findings verified by reading source code at specific line numbers
- Business logic edge cases verified by tracing code paths, not by modifying data
