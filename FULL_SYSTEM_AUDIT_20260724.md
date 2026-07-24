# SYSeducore — Full System Audit

**Date:** 2026-07-24
**Scope:** Entire system — `config/`, all 8 apps (~18.5k lines of Python), 46 templates (~17k lines), static JS/PWA, Docker/nginx/CI infra, migrations, test suite.
**Method:** File-by-file read of every non-generated source file, plus cross-cutting greps for authorization, timezone, money-type, soft-delete and N+1 patterns. Every finding below was verified by reading the actual code path.

> **Verification caveat:** Django is not installed in this environment, so `manage.py check --deploy`, `makemigrations --check` and the test suite could **not** be executed. Every issue below is derived from source reading, not from runtime output. Findings marked *(runtime-confirmable)* should be re-checked by running the code.

---

## Executive summary

| Severity | Count |
|---|---|
| **Critical** | 8 |
| **High** | 34 |
| **Medium** | 61 |
| **Low** | 33 |
| **Total** | **136** |

### The five things that matter most

1. **`.env` with the live `SECRET_KEY`, `DEBUG=True` and the DB password is committed to git** (SEC-01/02/03). `.gitignore` lists it, but the file was committed before being ignored, so git still tracks it. `DEBUG=True` combined with the production hostname means the deployed site very likely serves full tracebacks, disables SSL redirect, and issues non-secure cookies.
2. **Authorization is effectively "any logged-in user can do anything."** 100 views are guarded by authentication only (65 `@login_required` + 35 `@ajax_login_required`) against 3 `@supervisor_required` and 4 `@admin_required`. A `role='teacher'` account can mark payments paid, activate subscriptions, grant exceptions, mass-deactivate students, delete teachers/rooms/groups, and read the full financial report (AUTH-01…AUTH-12).
3. **Four features are dead on arrival** — they raise on first use and are never exercised by tests: booking creation (BUG-01), the monthly WhatsApp reminder cron (BUG-02), the `/api/attendance/scan/` endpoint (BUG-03), and the WhatsApp test page (BUG-04).
4. **The attendance-notification cron re-sends every message every 5 minutes, all day** (BUG-05) — it sets `notification_sent` but never filters on it. Every parent gets the same WhatsApp message dozens of times per session.
5. **Money is handled without an audit trail or a transaction.** `Payment.amount_paid` is a mutable running total with no receipt table, no `created_by`, no atomicity, and no over/under-payment guard (FIN-01…FIN-06).

---

## 1. Secrets, configuration & deployment

### SEC-01 — `.env` containing the production `SECRET_KEY` is tracked in git — **Critical**
`.env:2`, present in commits `abe4bd2`, `e0f15bc`, `7726770`.
`SECRET_KEY=fdJqJmsnrl9Z7JhrrHkZk2iS-...` is in the repository history. Anyone with repo access can forge session cookies, password-reset tokens and signed data. `.gitignore:14` lists `.env`, but gitignore does not untrack an already-committed file.
**Fix:** rotate the key, `git rm --cached .env`, purge from history, load from a secret store.

### SEC-02 — `DEBUG=True` in the deployed `.env` — **Critical**
`.env:3` together with `ALLOWED_HOSTS=...,sys.educore.software` (`.env:4`).
With `DEBUG=True`, `config/settings.py:297` skips the entire production security block: no `SECURE_SSL_REDIRECT`, no `SESSION_COOKIE_SECURE`, no `CSRF_COOKIE_SECURE`, no HSTS, no `X_FRAME_OPTIONS=DENY`. Django also serves full tracebacks with settings and SQL on any unhandled exception — and the codebase has many broad `except Exception` handlers that echo `str(e)` to the client regardless.

### SEC-03 — Database password committed — **Critical**
`.env:11` `DB_PASSWORD=educore123`; the same weak value is the compose default at `docker-compose.yml:13`.

### SEC-04 — Insecure `SECRET_KEY` fallback — **High**
`config/settings.py:26` — `default='django-insecure-change-this-in-production'`. If the env var is ever missing in production the app silently boots with a publicly known key instead of refusing to start.

### SEC-05 — `SECURE_PROXY_SSL_HEADER` trusted unconditionally — **High**
`config/settings.py:225`. The comment says "always set for reverse proxy," but if the gunicorn port is reachable directly (it is exposed on `0.0.0.0:8000` inside the compose network), a client can send `X-Forwarded-Proto: https` to make Django believe the connection is secure — defeating `SECURE_SSL_REDIRECT` and allowing "secure" cookies over plaintext.

### SEC-06 — nginx will cause an HTTPS redirect loop the moment `DEBUG=False` — **High**
`nginx.conf:44` listens on plain HTTP `1999` and forwards `X-Forwarded-Proto $scheme` (= `http`) at `nginx.conf:52`. There is no TLS server block anywhere. With `DEBUG=False`, `SECURE_SSL_REDIRECT=True` fires on every request → 301 to `https://` → the outer terminator forwards back over http → loop.
**Fix:** terminate TLS in nginx, or forward `$http_x_forwarded_proto` from the upstream terminator.

### SEC-07 — Report password is a hardcoded `888888` and the gate does nothing — **High**
`apps/reports/views.py:24` and `:35-36`. `report_password_required` returns immediately for any authenticated user — and every view it decorates is *also* `@login_required`, so the password branch is unreachable dead code. The "protected" financial reports are open to all roles. `tests/test_permissions.py:141` even asserts a teacher gets `200` on `/reports/financial/`.

### SEC-08 — Log file has no rotation — **Medium**
`config/settings.py:318-322` uses `logging.FileHandler` on `logs/django.log` at INFO for the root logger, with `SCAN_RECEIVED`/`SCAN_RESULT` lines per scan. Unbounded growth fills the volume.

### SEC-09 — Redis cache failure takes down login and scanning — **Medium**
`config/settings.py:231-239`: no `IGNORE_EXCEPTIONS`, no `SOCKET_TIMEOUT`. `django_ratelimit` uses this cache, so a Redis outage turns every rate-limited view (login, scanner) into a 500.

### SEC-10 — Deprecated `STATICFILES_STORAGE` setting — **Medium**
`config/settings.py:162`. Removed in Django 5.1; should be `STORAGES = {"staticfiles": {...}}`.

### SEC-11 — `os.makedirs` side effect at settings import — **Low**
`config/settings.py:342`. Crashes on a read-only filesystem before Django can report anything useful.

### SEC-12 — `CORS_ALLOWED_ORIGINS` hardcoded — **Low**
`config/settings.py:203-207`. Not env-driven, unlike `CSRF_TRUSTED_ORIGINS`; staging/dev hosts require a code change.

### SEC-13 — `SYSTEM_LOCKOUT` requires a code edit + redeploy — **Low**
`config/settings.py:77`. The kill-switch used by `apps/accounts/middleware.py:17` is a literal, not `config('SYSTEM_LOCKOUT', ...)`.

### SEC-14 — `SESSION_SAVE_EVERY_REQUEST=True` on the DB session backend — **Low**
`config/settings.py:214-215`. A session `UPDATE` on every request, including static and media, plus a second write from `SessionTimeoutMiddleware` (`middleware.py:48`).

### SEC-15 — `django-debug-toolbar` shipped in production requirements — **Low**
`requirements.txt:34`, never added to `INSTALLED_APPS`. Dead dependency in the production image.

### SEC-16 — All CSS/JS loaded from CDNs with no SRI — **Medium**
`templates/base.html:15,16,18,875` (jsDelivr Bootstrap + icons, Google Fonts). No `integrity`/`crossorigin` attributes, and no local fallback — a CDN outage or compromise takes down or takes over the whole UI. The PWA service worker (`static/sw.js:6-9`) also caches these cross-origin URLs.

---

## 2. Infrastructure — Docker, compose, CI/CD

### OPS-01 — `collectstatic` failure is swallowed, guaranteeing a runtime 500 — **High**
`Dockerfile:59` — `RUN python manage.py collectstatic --no-input || true`. With `CompressedManifestStaticFilesStorage`, a missing `staticfiles.json` manifest makes every `{% static %}` tag raise at render time. The build "succeeds" and the app 500s on the first page.

### OPS-02 — Container healthcheck breaks under production settings — **High**
`Dockerfile:65-66` and `docker-compose.yml:71`. The check GETs `/accounts/login/` and requires `200`. With `DEBUG=False`, `SECURE_SSL_REDIRECT` returns 301 and `requests` follows it to an https URL nothing is listening on → exception → container permanently `unhealthy`.

### OPS-03 — Container runs as root — **High**
`Dockerfile` has no `USER` directive. Combined with the bind mount below, a code-execution bug gets root on the host source tree.

### OPS-04 — Production compose bind-mounts the host source over the image — **High**
`docker-compose.yml:54` (`- .:/app`), repeated for `celery_worker:89` and `celery_beat:115`. The built image is discarded at runtime; whatever is on the host — including `.env`, which `.dockerignore:50` was careful to exclude from the image — is what actually runs.

### OPS-05 — `web` service has no restart policy — **Medium**
`docker-compose.yml:44-77`. `celery_worker`, `celery_beat` and `nginx` all have `restart: unless-stopped`; the web app and the database do not.

### OPS-06 — `/health/` is proxied but does not exist — **Medium**
`nginx.conf:68-72` proxies `/health/` to Django; `config/urls.py` defines no such route, so it 404s. The deploy workflow's smoke tests reference the same URL.

### OPS-07 — Dev compose port/CSRF mismatch — **Medium**
`docker-compose.dev.yml:17` publishes `3000:8000`, but `.env:5` `CSRF_TRUSTED_ORIGINS` lists only `localhost:1999` and the production domain. Every POST in dev fails CSRF validation.

### OPS-08 — Dev worker command needs a package that isn't installed — **Medium**
`docker-compose.dev.yml:26` runs `watchmedo`; `watchdog` is not in `requirements.txt`. The dev Celery worker exits immediately.

### OPS-09 — Every CI quality/security gate is `continue-on-error` — **High**
`.github/workflows/ci.yml` — Black, isort, Flake8, Bandit and Safety all set `continue-on-error: true`, which also makes `needs.<job>.result` report `success`. The final `ci-success` gate (line ~250) therefore passes regardless of what the scanners found. CI security is decorative.

### OPS-10 — The `django-checks` CI job can never pass — **High**
`.github/workflows/ci.yml` (django-checks) copies `.env.example` (which sets `DEBUG=True`) and runs `manage.py check --deploy --fail-level WARNING`. With DEBUG on, Django emits `security.W004/W008/W012/W016/W018`, so the job fails on every commit.

### OPS-11 — The deploy pipeline deploys nothing — **High**
`.github/workflows/deploy.yml` — the staging deploy, production deploy, migrations, backup and health-check steps are all `echo` placeholders with the real commands commented out. Anyone reading the green checkmark will believe a deployment happened.

### OPS-12 — Tag-triggered production deploys never run — **Medium**
`deploy.yml`: `deploy-production` has `needs: [build-and-test, deploy-staging]`, but `deploy-staging` only runs `if: github.ref == 'refs/heads/master'`. On a `v*` tag push, staging is skipped → the `needs` dependency is unsatisfied → production is skipped.

### OPS-13 — Trivy scans a nonexistent image tag — **Medium**
`.github/workflows/docker-build.yml`: the scan job references `:${{ github.sha }}`, but `docker/metadata-action` produces `type=sha,prefix={{branch}}-` (e.g. `master-abc1234`). The scan job also lacks `permissions: security-events: write`, so the SARIF upload would fail even if the scan succeeded.

### OPS-14 — Security-issue automation can never fire — **Medium**
`.github/workflows/dependency-review.yml`: `create-security-issue` is gated on `if: failure()`, but `dependency-check` is `continue-on-error`, so it never fails. The job also lacks `permissions: issues: write`.

### OPS-15 — Deprecated `actions/create-release@v1`; obsolete compose `version:` keys — **Low**
`deploy.yml` (post-deploy), `docker-compose.yml:1`, `docker-compose.dev.yml:1`.

### OPS-16 — `check_integrity.py` scans a hardcoded path from another machine — **Medium**
`check_integrity.py:77` — `Path('/root/.gemini/antigravity/scratch/SYSeducore/templates')`. Every `file_path.exists()` is False, so the script silently reports "0 issues" no matter what. Also a bare `except:` at line 73.

---

## 3. Authorization (systemic)

**Baseline:** 65 `@login_required` + 35 `@ajax_login_required` = 100 authenticated-only views. Only 3 `@supervisor_required` (`apps/students/views.py:202,311,398`) and 4 `@admin_required` (`apps/accounts/views.py:60,67,98,121`). `teacher_required` in `apps/accounts/decorators.py:50` is defined and never used.

### AUTH-01 — Any authenticated user can mark any payment fully paid — **Critical**
`apps/payments/api_views.py:105` (`mark_as_paid`) and `:63` (`record_payment`) — `@ajax_login_required` only. Reachable at `/api/payments/<id>/mark-paid/`. A teacher-role account can zero out the entire month's receivables.

### AUTH-02 — Any authenticated user can activate subscriptions and fabricate paid records — **Critical**
`apps/students/api_views.py:594` (`activate_subscription`). It marks every active enrollment's current-month `Payment` as `paid` with `amount_paid = fee` (lines 623-645), reactivates *all* previously removed enrollments (line 611), and writes **no `ActivityLog` entry**.

### AUTH-03 — Any authenticated user can settle payments from the scanner — **Critical**
`apps/attendance/views.py:324` (`scanner_pay_now`) and `:380` (`scanner_grace_period`). `scanner_grace_period` also extends the subscription and silently re-activates every inactive enrollment (lines 412-414).

### AUTH-04 — Any authenticated user can grant or revoke payment exceptions — **High**
`apps/attendance/views.py:430`, `:547`. The docstring says "Called from the scanner UI by admin/supervisor," but nothing enforces it. `exception_type` and `reason_type` are not validated against their `choices` either, so arbitrary strings get stored.

### AUTH-05 — Any authenticated user can enroll/unenroll students and set fee exemptions — **High**
`apps/students/api_views.py:159` (`add_to_group`), `:221` (`remove_from_group`), `apps/teachers/views.py:817` (`booking_student_enroll`). `financial_status` is taken straight from POST with no validation, so a user can set themselves — or anyone — to `exempt`.

### AUTH-06 — Any authenticated user can bulk-deactivate students — **High**
`apps/students/api_views.py:553` (`bulk_action`), and `apps/students/views.py:519` (`student_toggle_status`, `@login_required` only while create/update/delete correctly use `@supervisor_required`).

### AUTH-07 — All teacher / room / group / subject CRUD is authentication-only — **High**
`apps/teachers/views.py` — every view from `teacher_create:121` through `subject_delete:496` and the booking views. Any role can delete teachers, rooms and groups, and set `standard_fee` / `center_percentage`.

### AUTH-08 — Session cancellation and teacher check-in are unrestricted — **High**
`apps/attendance/views.py:83` (`record_teacher_attendance`), `:100` (`cancel_session`). Neither writes an `ActivityLog` entry, so cancelled sessions are untraceable.

### AUTH-09 — Financial reports and teacher settlements open to all roles — **High**
`apps/reports/views.py:412,479,772` (payments / financial / tsfya — the password gate is inert, see SEC-07) and `apps/payments/views.py:150` (`teacher_settlement`).

### AUTH-10 — The audit log itself is readable by everyone — **Medium**
`apps/reports/views.py:532`. `admin_required` is imported on line 535 and never applied. The log contains usernames and IP addresses.

### AUTH-11 — Recycle bin: any user can view and restore deleted records — **Medium**
`apps/reports/views.py:575` (`recycle_bin`) and `:604` (`recycle_restore`). Only `recycle_permanent_delete:648` and `recycle_empty:702` check `request.user.role != 'admin'` — and they do it inline rather than via the decorator.

### AUTH-12 — Every WhatsApp view is authentication-only — **High**
`apps/notifications/views.py:31-540`. Any authenticated user can message every parent in the system, with an arbitrary body, via `send_bulk_custom_message:498` — which accepts a free-form phone list and does not even log the messages it sends.

### AUTH-13 — Role decorators redirect instead of returning 403 — **Medium**
`apps/accounts/decorators.py:33,46,59` use `user_passes_test`, which redirects to `LOGIN_URL` on failure. For an already-authenticated user, `login_view:25-26` bounces them straight back to the dashboard — a silent no-op with no error message. On AJAX endpoints it returns an HTML redirect that breaks the caller's `response.json()`.

### AUTH-14 — `PermissionDenied` imported but unused — **Low**
`apps/accounts/decorators.py:4`.

---

## 4. Broken features (raise or no-op on first use)

### BUG-01 — Booking creation is completely broken — **Critical**
`apps/teachers/views.py:666-679` calls `Group.objects.create(..., subject=subject, ...)`. **`Group` has no `subject` field** (`apps/teachers/models.py:158-228`); subjects live on `Teacher.subjects`. Every submission raises `TypeError`, is swallowed by `except Exception` at line 698, and the user gets "حدث خطأ" with a redirect. The whole `templates/teachers/bookings/create.html` flow (571 lines of UI) is unusable.
Same view, line 668: `teacher if teacher else Teacher.objects.first()` — when no teacher is chosen it silently assigns an **arbitrary** teacher.

### BUG-02 — The monthly payment-reminder cron raises every month — **High**
`apps/notifications/tasks.py:84` calls `notification_service.send_monthly_reminders()`. `NotificationService` (`apps/notifications/services.py:367-434`) has no such method — only `send_monthly_reminder` (singular, 4 args). Scheduled at `config/settings.py:258-261` for the 1st of each month; raises `AttributeError` and no reminder is ever sent.

### BUG-03 — `/api/attendance/scan/` always returns a 500 — **High**
`apps/attendance/api_views.py:29-45` does `result['student'].student_id`, but `AttendanceService.process_scan` returns `student` as a **dict** (`apps/attendance/services.py:445-450`). `AttributeError` → caught at line 62 → 500 with the raw message. (The working scanner uses `views.process_student_code`; this duplicate endpoint is broken.)

### BUG-04 — The WhatsApp test page 500s — **High**
`apps/notifications/views.py:454` renders `notifications/test.html`. That template does not exist. `GET /notifications/test/` → `TemplateDoesNotExist`.

### BUG-05 — Attendance notifications are re-sent every 5 minutes, all day — **Critical**
`apps/notifications/tasks.py:21-25`: the session queryset filters on date, cancellation and group activity — but **not** on `notification_sent`. The flag is set at line 78 and never read. Every run (every 5 minutes per `config/settings.py:254-257`) re-sends a WhatsApp message to every parent of every student in every session that started more than 10 minutes ago. For a session at 16:00, parents keep receiving the same message until midnight — ~96 duplicate messages per parent per session, at full API cost.

### BUG-06 — `payment_report`'s month filter crashes on PostgreSQL — **High** *(runtime-confirmable)*
`apps/reports/views.py:431` — `payments.filter(month__startswith=month)` where `month` is a `DateField`. Pattern lookups skip value coercion, so the SQL becomes `"payments"."month" LIKE '2026-02%'`; PostgreSQL rejects `date ~~ text`. SQLite stores dates as text, which is why `config/settings_test.py` masks this in the test suite.

### BUG-07 — Re-enrolling a student into a group they were removed from silently fails — **High**
`apps/students/views.py:359-367`. `current_group_ids` only contains *active* enrollments, so a previously removed group looks "new" and goes through `get_or_create` — which **gets** the existing inactive row and ignores `defaults`. `is_active` stays `False`. Same block: changes to `financial_status` / `custom_fee` for **existing** enrollments are never applied — the form shows the fields, the view discards them.

### BUG-08 — `bulk_action(delete)` does not delete — **High**
`apps/students/api_views.py:570-572`. The `delete` branch runs `students.update(is_active=False)` and reports "تم حذف N طالب". Nothing is soft-deleted; the students never reach the recycle bin and still appear in every list.

### BUG-09 — `views.record_payment` is unroutable and would crash — **Medium**
`apps/payments/views.py:167`. Not referenced in `apps/payments/urls.py`. Line 173 does `float(...)` then `payment.amount_paid += amount` — `Decimal + float` raises `TypeError`.

### BUG-10 — `prepare_production` is doubly broken — **Medium**
`apps/core/management/commands/prepare_production.py:19` imports `MessageTemplate` from `apps.notifications.models`, which does not exist (it is `WhatsAppTemplate`) → `ImportError`. And `apps.core` is **not in `INSTALLED_APPS`** (`config/settings.py:52-59`), so Django never discovers the command anyway.

### BUG-11 — `contact_list` filters are no-ops — **Medium**
`apps/notifications/views.py:366,368` — `student_phone__isnull=False` / `parent_phone__isnull=False`. Both columns are `blank=True` without `null=True`, i.e. `NOT NULL`, so the filters match every row. Should be `.exclude(student_phone='')`.

### BUG-12 — The entire `static/js/` layer is dead and broken — **Medium**
No template loads any of it (`templates/base.html` contains zero `{% static %}` tags). Beyond being unused, `static/js/utils/api.js:60-99` — `get`, `post`, `put` and `delete` all spread `...defaultOptions`, a variable scoped inside `request()` → `ReferenceError` on every call. `static/js/main.js:118` posts to `/api/auth/login/`, a URL that does not exist. ~2,000 lines of dead code (also `static/css/base.css`).

### BUG-13 — `utils/` is dead code — **Medium**
`utils/barcode_generator.py` (201 lines) and `utils/pdf_generator.py` (308 lines) are imported nowhere. `pdf_generator.py:114` also uses naive `datetime.now()`.

### BUG-14 — `apps/tests_comprehensive.py` is a broken 247-line stub — **Medium**
Zero `def test_`. At import it calls `django.setup()` (line 12), inserts a stale absolute path `/root/.gemini/antigravity/scratch/SYSeducore` (line 11) and mutates `settings.ALLOWED_HOSTS` (line 16). Because it lives inside the `apps` package, the test runner may import it and re-run `django.setup()`.

### BUG-15 — `AttendanceService.update_billing_cycle` is never called — **Medium**
`apps/attendance/services.py:969`. Dead code; `check_billing_cycles` in `tasks.py` reimplements it separately.

### BUG-16 — `check_billing_cycles` never sets the cycle dates it documents — **Medium**
`apps/attendance/tasks.py:78-143`. The docstring promises to update `StudentGroupEnrollment` cycle dates; `cycle_start_date`/`cycle_end_date` are read (line 108) but never written, so they stay `None` forever and the cycle always falls back to calendar month.

### BUG-17 — `export_students` admin action exports nothing — **Low**
`apps/students/admin.py:74-77` — displays a message and returns.

---

## 5. Data integrity & correctness

### DATA-01 — `groups_count` annotation is inflated by a cartesian join — **High**
`apps/students/views.py:37-41` and `apps/students/api_views.py:463`:
```python
Count('groups', filter=Q(group_enrollments__is_active=True))
```
`groups` (M2M) and `group_enrollments` (reverse FK) are two independent joins, so the rows multiply and the count is wrong for any student in more than one group. The `with_groups` / `no_groups` filters (`views.py:67-70`) are built on this broken number. Should be `Count('group_enrollments', filter=Q(group_enrollments__is_active=True))`.

### DATA-02 — Unique constraints collide with soft delete — **High**
`Student.student_code` (`apps/students/models.py:48-54`), `Room.name` (`apps/teachers/models.py:13`), `Teacher.email` (`:68`) are `unique=True` at the DB level, but the models are soft-deletable. `StudentForm.clean_student_code` (`apps/students/forms.py:91`) checks uniqueness against `Student.objects` — alive rows only — so reusing a deleted student's code passes validation and then fails with `IntegrityError` at save. Same for recreating a deleted room by name.

### DATA-03 — A second teacher with a blank email raises `IntegrityError` — **High**
`apps/teachers/models.py:68-74` — `EmailField(blank=True, null=True, unique=True)`. `TeacherForm` (`apps/teachers/forms.py:38`) makes email optional, and Django form fields clean empty input to `''`, not `None`. The first blank-email teacher stores `''`; the second violates the unique constraint. The field is documented as "حقل اختياري".

### DATA-04 — `Group` has two conflicting sources of schedule truth — **High**
Legacy `Group.schedule_day` / `schedule_time` / `duration_minutes` vs. the `GroupSchedule` model (`apps/teachers/models.py:329-397`). `GroupForm.save_with_schedules` (`forms.py:108-112`) writes only the **first** day back to the legacy fields. Everything below then reads the legacy fields and therefore ignores every day but the first:
- `apps/teachers/views.py:776` (`booking_calendar`)
- `apps/teachers/api_views.py:95,199,355` (room schedule / availability check)
- `apps/attendance/views.py:186` (`today_sessions`)
- `apps/attendance/tasks.py:35` and `apps/notifications/tasks.py:26` (auto-absence + notifications trigger at the wrong time)
- `apps/teachers/models.py:273` (`Group.clean` room-overlap check misses conflicts)
- `apps/attendance/services.py:503` (rejection message shows the wrong day)
Only `process_scan` (`services.py:249`) and the dashboard (`reports/views.py:201`) consult `GroupSchedule`.

### DATA-05 — `GroupSchedule` overlap validation never runs — **Medium**
`apps/teachers/models.py:371` defines `clean()`, but `GroupForm.save_with_schedules` (`forms.py:120-125`) uses `objects.create()`, which does not call `full_clean()`. Double-booked rooms are accepted silently. The same method deletes all existing schedules before recreating them (line 118) with no transaction — a failure mid-loop loses the group's schedule entirely.

### DATA-06 — Money is parsed as `float` — **Medium**
`apps/students/views.py:234,249,251,356`; `apps/teachers/views.py:622,623`; `apps/payments/views.py:173`. Assigning binary floats to `DecimalField` reintroduces the rounding errors `Decimal` exists to avoid. `apps/students/api_views.py:187,202` is worse — it assigns the **raw POST string** to `custom_fee`, so non-numeric input raises `decimal.InvalidOperation` as an unhandled 500.

### DATA-07 — No validation on fees or percentages — **Medium**
`GroupForm` (`apps/teachers/forms.py:61-98`) applies no `MinValueValidator` to `standard_fee` and no 0-100 bound to `center_percentage`. Negative fees and a 500% center share are accepted.

### DATA-08 — `student_code` generation is not concurrency-safe on SQLite, and races on an empty table — **Medium**
`apps/students/models.py:208-226`. `select_for_update()` on a regex-filtered queryset locks only *matching* rows — with an empty table nothing is locked and two concurrent creates both return `'1001'`. SQLite ignores `select_for_update()` entirely.

### DATA-09 — `financial_status` accepted without validating against `choices` — **Medium**
`apps/students/api_views.py:165,185,198`; `apps/teachers/views.py:638`. `apps/students/views.py:228,350` *does* validate — the API paths do not, so arbitrary 15-character strings reach the DB. Django `choices` are not enforced at the database level.

### DATA-10 — The `per_session` financial status is not implemented — **Medium**
It is offered as a choice (`apps/students/models.py:384`) but `Student.get_monthly_fee_for_group` (`models.py:282-296`) falls through to `standard_fee`, and `check_financial_status` (`services.py:657`) treats it as `normal`. Per-session students are billed a full month.

### DATA-11 — `sessions_per_month = 0` blocks every student — **Medium**
`apps/attendance/services.py:706-714`: `if sessions_count >= sessions_limit` with `sessions_limit = 0` is always true, so everyone in that group is rejected with "تم استنفاد جميع الحصص". `sessions_per_month` is a `PositiveIntegerField` with no minimum.

### DATA-12 — Soft-deleted students still generate absences and appear in rosters — **Medium**
`apps/attendance/tasks.py:47-50` and `apps/notifications/tasks.py:36-39` query `StudentGroupEnrollment` directly; the FK join does not filter `student.deleted_at`. `apps/students/views.py:399-421` soft-deletes a student without deactivating their enrollments.

### DATA-13 — `Payment.get_or_create` as a side effect of read paths — **Medium**
`apps/attendance/services.py:111` (`get_instant_status`) and `:742` (`check_financial_status`) create payment rows during what is nominally a check. `get_instant_status` does so even for exempt students.

### DATA-14 — Browsing an old month in the payments list back-fills that month with today's fees — **High**
`apps/payments/views.py:104` calls `_ensure_monthly_payments(month_date)` on every page load, using whatever `?month=` the user typed. Selecting `2020-01` creates a full set of `Payment` rows for January 2020 priced at current fees. The function (`views.py:20-88`) also iterates **every** active enrollment on every request.

### DATA-15 — Exempt students are counted as "paid" — **Medium**
`apps/payments/views.py:66-73` creates zero-fee rows with `status='paid'`, inflating the paid count and collection rate in `payment_list`, `tsfya` and the dashboard.

### DATA-16 — `_activate_student_for_payment` silently creates enrollments and re-activates records — **Medium**
`apps/payments/api_views.py:32-42`: `get_or_create` enrolls the student in the payment's group even if they were never enrolled, and forces `student.is_active = True`, overriding a deliberate deactivation. `Student.activate_subscription` (`apps/students/models.py:314`) does the same.

### DATA-17 — Attendance `'late'` status is unreachable — **Medium**
`check_strict_time` (`apps/attendance/services.py:627-631`) always returns `status='present'` — the comment says so explicitly. But `'late'` is a valid choice (`models.py:42`) and is counted separately in the dashboard (`reports/views.py:128`), attendance report (`:383`), CSV export (`attendance/views.py:269`) and stats APIs. Those counters are permanently zero.

### DATA-18 — Two Celery tasks both auto-mark absences — **Medium**
`apps/attendance/tasks.py:11` (every 2 min) and `apps/notifications/tasks.py:11` (every 5 min) implement the same 10-minute auto-absence rule with slightly different logic. Only `ignore_conflicts=True` prevents duplicate-key errors.

### DATA-19 — Auto-created absences do not update `sessions_attended` — **Medium**
`apps/attendance/tasks.py:67` uses `bulk_create`, which bypasses `update_payment_sessions`. `update_payment_sessions`'s own docstring (`services.py:940-943`) states absences must count toward the billing cycle.

### DATA-20 — `_count_overdue_months` counts payment rows, not months — **Medium**
`apps/attendance/services.py:43-50`. A student in 3 groups with one unpaid month is reported as 3 overdue months in the scanner dossier.

### DATA-21 — `_calculate_attendance_rate` can exceed 100% — **Medium**
`apps/attendance/services.py:66-85`. `total_sessions` is scoped to enrolled groups, but `attended` counts attendance across **all** groups with no upper date bound.

### DATA-22 — `get_total_paid_amount` ignores partial payments — **Medium**
`apps/students/models.py:365-372` filters `status='paid'` only.

### DATA-23 — Settlement excludes inactive/deleted groups — **Medium**
`apps/payments/services.py:18` and `apps/reports/views.py:508` filter `is_active=True`, so revenue from a group deactivated mid-month vanishes from the teacher's settlement.

### DATA-24 — Invalid `ActivityLog.action` values written — **Medium**
`apps/reports/views.py:632` writes `action='update'` and `:684` writes `action='delete'` — neither is in `ACTION_CHOICES` (`apps/attendance/models.py:95-125`). `get_action_display()` returns the raw string and the filter dropdown cannot select them. `recycle_empty:760` mislabels a bin purge as `'student_delete'`.

### DATA-25 — `recycle_empty` hard-deletes financial history — **High**
`apps/reports/views.py:702-768`. One admin POST permanently destroys `Attendance` and `Payment` rows for every soft-deleted student (lines 725-727) and every soft-deleted group (lines 737-740). This is irreversible accounting-record destruction with no export, no backup and no per-item confirmation.

### DATA-26 — `Subject` deletion is a hard delete — **Medium**
`apps/teachers/views.py:508`. Unlike every other entity, subjects bypass the recycle bin and silently clear the M2M rows on all teachers.

### DATA-27 — `Subject.get_or_create(name=...)` ignores the composite key — **Medium**
`apps/teachers/views.py:650`. `Subject` is unique on `(name, education_stage)` (`models.py:54`), so the same name across two stages raises `MultipleObjectsReturned`.

### DATA-28 — Phone normalization is inconsistent between forms — **Medium**
`StudentForm._clean_phone` (`apps/students/forms.py:98-111`) stores `01xxxxxxxxx`; `StudentQuickForm.clean_parent_phone` (`:142-150`) stores `+201xxxxxxxxx`. `WhatsAppService._format_phone_number` (`apps/notifications/services.py:199-215`) then force-prefixes `20` onto anything that does not already start with it — mangling non-Egyptian numbers.

### DATA-29 — Room capacity is compared against an aggregate across all sessions — **Medium**
`apps/teachers/views.py:248` and `apps/teachers/api_views.py:53,134`. Summing enrollments across *every* group in a room and comparing to capacity treats a room used by 5 groups as 5× over capacity. Capacity is per-session, not cumulative. `available_groups` (`apps/students/api_views.py:341`) can therefore report negative availability.

### DATA-30 — Admin can bypass all group validation via an Arabic substring match — **Medium**
`apps/teachers/admin.py:168-178` decides whether to skip validation by testing `if 'تعارض' in str(e)`. Any change to the message text silently converts a "warn and save" into a hard 500, and `skip_validation=True` also bypasses the education stage/year check.

---

## 6. Timezone correctness

The project runs `USE_TZ=True` with `TIME_ZONE='Africa/Cairo'` (UTC+2/+3). Sixteen call sites use `timezone.now().date()`, which yields the **UTC** date. Between 00:00 and 02:00/03:00 Cairo time these are off by one day.

### TZ-01 — Dashboard session status is computed in UTC — **High**
`apps/reports/views.py:170-183`: `now = timezone.now()` then `current_time = now.time()` is compared against `grp.schedule_time`, which is local. At 17:00 Cairo (14:00 UTC) a 16:00 session is reported as "upcoming" instead of "ongoing". Every session's status badge is 2-3 hours out of phase.

### TZ-02 — Dashboard mixes UTC date with local day name — **Medium**
`apps/reports/views.py:103` (`timezone.now().date()`) vs `:105` (`AttendanceService_get_day_name()`, which uses `localtime()`). After midnight Cairo they disagree, so the schedule and the session counts describe different days.

### TZ-03 — Attendance stats and CSV exports use the UTC date — **Medium**
`apps/attendance/views.py:128,182,244`.

### TZ-04 — Celery tasks resolve "today" in UTC — **Medium**
`apps/attendance/tasks.py:24`, `apps/notifications/tasks.py:19`.

### TZ-05 — Subscription expiry evaluated in UTC — **Medium**
`apps/students/models.py:304,311,330`. A subscription expires up to 3 hours early relative to the local day.

### TZ-06 — First-month detection uses the UTC date — **Medium**
`apps/attendance/services.py:651` — `first_attendance.scan_time.date()` on a UTC-aware datetime. A scan just after midnight Cairo is attributed to the previous month, flipping the strict first-month payment rule.

### TZ-07 — ID card and bulk report dates in UTC — **Low**
`apps/students/views.py:445,469`; `apps/notifications/services.py:146`.

### TZ-08 — `payment_date` assigned a `date` to a `DateTimeField` — **Low**
`apps/payments/admin.py:45`. Django coerces it to naive midnight and emits a `RuntimeWarning`.

### TZ-09 — `pytz` is used but not declared — **High**
`apps/attendance/services.py:231,587` (and `tests.py:388,678`) `import pytz` and call the pytz-only `localize()` API. **`pytz` is absent from `requirements.txt`.** It currently resolves as a transitive dependency; the moment that changes, the scanner — the core function of the system — raises `ImportError` on every scan. Django 5 uses `zoneinfo`; this code should too.

---

## 7. Performance & scalability

### PERF-01 — Student list loads every student with no pagination — **High**
`apps/students/views.py:37-96`. The queryset is fully materialized and then iterated in Python to attach payment flags. Add `Group` filters, a prefetch of enrollments, and 4 more aggregate queries.

### PERF-02 — Students API renders 100 barcodes per request — **High**
`apps/students/api_views.py:490-493`. Each `get_barcode_base64()` rasterizes a Code128 PNG at 300 dpi. 100 per request, synchronously. The docstring claims pagination; there is none (a silent `[:100]` truncation).

### PERF-03 — Bulk WhatsApp sends run synchronously in the request thread — **High**
`apps/notifications/views.py:156-183` and `:267-289`; `services.py:87-98`. Each send is a blocking HTTP call with a 10-second timeout. A 100-student group can block for ~1000 s — far past gunicorn's 120 s timeout (`Dockerfile:69`), so the worker is killed mid-send with messages half-delivered and no idempotency.

### PERF-04 — `room_statistics_api` walks every room three times with per-group counts — **Medium**
`apps/teachers/api_views.py:256-303`. Roughly `3 × rooms × groups` queries per call.

### PERF-05 — Dashboard issues 60+ queries — **Medium**
`apps/reports/views.py:98-349`: the 7-day trend loop alone is 28 queries (lines 251-258), plus the groups loop, `GroupSchedule.objects.get` per group (line 215), and ~20 aggregates.

### PERF-06 — `tsfya` runs 7 queries per group — **Medium**
`apps/reports/views.py:814-836`.

### PERF-07 — `financial_report` is N+1 over teachers — **Medium**
`apps/reports/views.py:507-519`, plus 4 aggregates × 12 months (lines 488-503).

### PERF-08 — Settlement is N+1 over payments — **Medium**
`apps/payments/services.py:105-131` — an enrollment lookup **and** a fee lookup per payment row.

### PERF-09 — Enrollment counts recomputed in loops — **Medium**
`apps/teachers/views.py:779` (`booking_calendar`), `apps/students/api_views.py:321` (`available_groups`), `apps/teachers/api_views.py:35,99,119,364`.

### PERF-10 — `Group.save()` calls `full_clean()` on every save — **Medium**
`apps/teachers/models.py:302-304`, and `clean()` (line 273) iterates every other group in the same room/day. Bulk operations degrade quadratically.

### PERF-11 — `today_sessions` creates rows during a GET stats poll — **Medium**
`apps/attendance/views.py:194-198`. A dashboard poll writes a `Session` row for every group scheduled today.

### PERF-12 — Scanner builds a full dossier on every scan — **Medium**
`apps/attendance/services.py:204` calls `build_student_dossier` before any validation — enrollments, a payment lookup per group, monthly stats, attendance rate. Paid on rejected scans too.

### PERF-13 — `check_billing_cycles` walks every active enrollment every 6 hours — **Medium**
`apps/attendance/tasks.py:96-141`, 2+ queries each.

### PERF-14 — Admin list pages are N+1 — **Medium**
`apps/students/admin.py:56` (`get_groups`), `apps/teachers/admin.py:38,94` (`get_groups_count`), `apps/attendance/admin.py` (`get_attendance_count`). No `get_queryset` override with `prefetch_related`.

### PERF-15 — No pagination on teacher/group/room/contact/user lists — **Medium**
`apps/teachers/views.py:88,294,175`; `apps/notifications/views.py:382`; `apps/accounts/views.py:62`.

### PERF-16 — Repeated `.count()` calls on the same queryset — **Low**
`apps/reports/views.py:591-595` (8 counts), `apps/notifications/views.py:337-343`, `apps/payments/views.py:127-132`.

---

## 8. Frontend, templates & PWA

### FE-01 — Stored XSS in the available-groups renderer — **High**
`templates/students/list.html:1046-1056` and `templates/students/detail.html:556-568` interpolate `group.group_name`, `group.teacher_name`, `group.room_name` into `innerHTML` with **no escaping** (the `.replace(/'/g, "\\'")` on line 1047 only patches the `onclick` string, not the HTML body). A group or teacher named `<img src=x onerror=...>` executes in every user's browser. Given AUTH-07 (any role can create groups), a teacher-role account can plant a payload that runs with an admin's session — and AUTH-01/02 mean that session can move money.
**Fix:** the codebase already has the right helper — `escHtml()` at `templates/attendance/scanner.html:1406-1411`, which `renderDossier` uses correctly throughout. Reuse it.

### FE-02 — JSON injected into JS without `json_script` — **Medium**
`templates/reports/dashboard.html:862` (`{{ week_attendance_json|safe }}`) and `templates/reports/financial.html:260` (`JSON.parse('{{ monthly_data|safe }}')` — JSON inside single quotes, so any apostrophe in the data breaks the page). Not currently attacker-controlled, but `|safe` on JSON is a latent hole. Use `{{ data|json_script:"id" }}`.

### FE-03 — Service worker caching is fragile — **Medium**
`static/sw.js:3-11`: `cache.addAll` rejects wholesale if **any** asset fails, so a single CDN hiccup means nothing is precached. The list includes `'/'` (a redirect to `/reports/`) and three cross-origin CDN URLs. It also precaches `/static/js/main.js` and `/static/css/base.css`, neither of which the app uses (BUG-12). The repo's `CACHE_CLEAR_INSTRUCTIONS.md` and `CLEAR_CACHE_INSTRUCTIONS.sh` suggest this has already caused stale-asset incidents.

### FE-04 — `math_filters.add` shadows Django's built-in `add` — **Medium**
`apps/reports/templatetags/math_filters.py:33`. Any template doing `{% load math_filters %}` silently gets float arithmetic in place of Django's `add`, changing string concatenation and integer behavior. The filters also catch `ValueError` but not `TypeError`, so a `None` value raises during rendering; `div` catches `ZeroDivisionError` while `mul`/`sub`/`add` do not need it. All four coerce `Decimal` money to `float`.

### FE-05 — Hardcoded API URLs bypass `{% url %}` — **Low**
`templates/students/detail.html:668`, `templates/payments/list.html:447,462`. Most of the codebase correctly uses `{% url %}` with a `.replace('0', id)` trick; these three drift if routes change.

### FE-06 — Arabic CSV export has no BOM — **Medium**
`apps/attendance/views.py:257-309`. The CSV is returned as a JSON string with no `﻿`; Excel renders Arabic as mojibake.

### FE-07 — Sticker PDF silently loses Arabic — **Low**
`apps/students/services/sticker_pdf.py:29-48`: `_font_registered = True` is set *before* registration is attempted, and if neither Cairo nor DejaVu is present `AR_FONT` stays `'Helvetica'`, which cannot render Arabic. Names are also truncated to 10 characters (line 86).

### FE-08 — Verified clean: CSRF — *(informational)*
Seven templates contain `<form>` without `{% csrf_token %}` (`reports/attendance.html`, `reports/payments.html`, `reports/tsfya.html`, `reports/activity_log.html`, `notifications/message_history.html`, `notifications/contact_list.html`, `teachers/bookings/search.html`) — all are `method="get"` filter forms. No issue.

---

## 9. Authentication & session handling

### AUTHN-01 — Rate limits are shared by all users behind the proxy — **High**
`apps/accounts/views.py:23` (`5/m`), `apps/attendance/views.py:25` and `apps/attendance/api_views.py:10` (`30/m`). `django_ratelimit`'s `key='ip'` reads `REMOTE_ADDR`, which behind nginx (`nginx.conf:48`) is always the proxy's container IP. **The entire centre shares one bucket:** 5 logins per minute and 30 scans per minute system-wide. A busy reception desk will lock itself out.
**Fix:** a key function reading the leftmost trusted `X-Forwarded-For` entry — the pattern already exists in `ActivityLog.log` (`apps/attendance/models.py:174-178`).

### AUTHN-02 — Login rate limit also counts page views — **Medium**
`apps/accounts/views.py:23` has no `method='POST'`, so five GETs of the login page exhaust the quota.

### AUTHN-03 — Password validators are configured but never applied — **High**
`config/settings.py:119-133` defines four validators. `UserCreateForm.save` (`apps/accounts/forms.py:72`) and `UserUpdateForm.save` (`:103`) call `set_password()` directly without `validate_password()`. An admin can set `1` as a password.

### AUTHN-04 — Generated passwords are shown in a flash message — **Medium**
`apps/accounts/views.py:87`. The plaintext password is stored in the DB-backed session and rendered in the page. There is also no way for a user to change their own password — `apps/accounts/urls.py` has no password change/reset routes at all.

### AUTHN-05 — An admin can lock themselves out — **Medium**
`user_toggle_status` (`apps/accounts/views.py:127`) guards against self-deactivation, but `UserUpdateForm` (`apps/accounts/forms.py:88`) exposes both `is_active` and `role`, so the same admin can demote or deactivate themselves through the edit form. No "last admin" check exists.

### AUTHN-06 — Dead inactive-user branch — **Low**
`apps/accounts/views.py:36-41`. `ModelBackend.authenticate` already returns `None` for inactive users, so `'حسابك غير نشط'` is never shown — inactive users see "wrong username or password".

### AUTHN-07 — CSRF failures redirect to login — **Medium**
`apps/accounts/views.py:16-19` (wired at `config/settings.py:222`). Real CSRF misconfiguration is masked as "session expired", and AJAX POSTs receive an HTML redirect instead of a JSON error.

### AUTHN-08 — `SessionTimeoutMiddleware` duplicates `SESSION_COOKIE_AGE` — **Low**
`apps/accounts/middleware.py:29-51` reimplements a 1-hour idle timeout already provided by `SESSION_COOKIE_AGE=3600` + `SESSION_SAVE_EVERY_REQUEST=True`, adding a session write on every request including static files.

---

## 10. Error handling & observability

### QUAL-01 — Raw exception text returned to clients — **High**
23 handlers return `str(e)` in the response body: `apps/teachers/api_views.py:75,161,247,324,405`; `apps/teachers/views.py:699,855`; `apps/students/api_views.py:62,153,665,696`; `apps/attendance/views.py:63,375,425,528`; `apps/attendance/api_views.py:65`; `apps/payments/api_views.py:100,140`; `apps/notifications/views.py:188,295,493,540`; `apps/reports/views.py:755`. These leak model names, SQL fragments and file paths — and with `DEBUG=True` (SEC-02) the surrounding HTML error pages leak far more.

### QUAL-02 — Bare `except:` — **Medium**
`apps/students/api_views.py:126,494`. Swallows `KeyboardInterrupt` and `SystemExit`.

### QUAL-03 — Silent failure swallowing — **Medium**
`apps/students/models.py:267` (`get_barcode_base64` returns `''` on any error → blank ID cards with no signal); `apps/students/views.py:283`; `apps/teachers/views.py:266,368`; `apps/attendance/views.py:510`.

### QUAL-04 — Financial operations are not atomic — **High**
`apps/payments/api_views.py:63-101` and `:105-140`: payment mutation, subscription activation, enrollment reactivation and activity logging span four writes with no `transaction.atomic()`. Same in `apps/attendance/views.py:324-375`, `apps/students/api_views.py:594-666`, and `AttendanceService.process_scan` (`services.py:169-466`), which creates sessions, attendances and payments across multiple groups unatomically — concurrent double-scans race on `unique_together`.

### QUAL-05 — No `ActivityLog` for the money-moving paths — **High**
`scanner_pay_now` (`apps/attendance/views.py:324`), `activate_subscription` (`apps/students/api_views.py:594`), `cancel_session` (`apps/attendance/views.py:100`), the initial-payment creation in `student_create` (`apps/students/views.py:255`) and all four `PaymentAdmin` bulk actions (`apps/payments/admin.py:41-77`, including `clear_payments`, which zeroes payments) write nothing to the audit log. The system therefore cannot answer "who marked this paid?"

### QUAL-06 — No payment receipt trail — **High**
`Payment` (`apps/payments/models.py`) has no `created_by`, no receipt/transaction child table, and `amount_paid` is a mutable running total. `record_payment` does `amount_paid += amount` with no guard against negative or over-payment (`MinValueValidator` is only enforced by `full_clean()`, which `save()` does not call), so payments can be silently reversed. `PaymentAdmin.list_editable` (`admin.py:11`) also allows editing `amount_paid` and `status` independently and inconsistently, straight from the list page.

### QUAL-07 — No 404/500 handlers, no Sentry, no request IDs — **Medium**
`config/urls.py` defines no `handler404`/`handler500`. The only observability is a rotationless log file.

---

## 11. Tests

### TEST-01 — The permission tests document the gaps instead of closing them — **High**
`tests/test_permissions.py:49` — `self.assertIn(response.status_code, [200, 302, 403])` for a teacher reading the activity log: an assertion that cannot fail. `:141` `test_teacher_access_financial_report` asserts a teacher gets **200** on the financial report. The suite locks in the AUTH findings above as intended behaviour.

### TEST-02 — 441 tests, but every Critical/High bug in §4 is untested — **High**
No test exercises `booking_create` (BUG-01), `send_monthly_reminders_task` (BUG-02), `api_views.process_scan` (BUG-03), `test_whatsapp` (BUG-04), the `notification_sent` filter (BUG-05), or `?month=` on the payment report (BUG-06).

### TEST-03 — SQLite test settings mask a PostgreSQL-only failure — **Medium**
`config/settings_test.py:8-13` uses SQLite while production is PostgreSQL (`.env:8`). BUG-06 passes under SQLite and fails in production. `select_for_update` (DATA-08) is likewise a no-op under SQLite.

### TEST-04 — MD5 password hasher in test settings — **Low**
`config/settings_test.py:16-18`. Fine for speed, but it means AUTHN-03 (missing password validation) can never be caught by a test.

---

## 12. Documentation & repository hygiene

### DOC-01 — `.env.example` describes a decommissioned integration — **Medium**
`.env.example:22-24` documents `ULTRAMSG_*` and omits `WASENDER_API_TOKEN` — the variable the live integration actually reads (`apps/notifications/services.py:18`). `REPORTS_PASSWORD` (`apps/reports/views.py:24`) is undocumented too, so deployments silently run with `888888`.

### DOC-02 — Dead UltraMsg code path — **Medium**
`apps/students/api_views.py:98-148` still calls the UltraMsg image API. With the settings empty by default it always returns "إعدادات الواتساب غير مكتملة", so "send barcode via WhatsApp" is a permanently broken button. It also writes a temp file to `MEDIA_ROOT/temp` (line 103) that leaks if the request throws, and blocks a worker for up to 30 seconds (line 120).

### DOC-03 — 50+ status/bugfix markdown files at the repo root — **Low**
`BUGFIX_*.md`, `DEPLOYMENT_*.md`, `WHATSAPP_*.md`, etc. Several claim fixes that this audit found still present (e.g. `MASTER_BUG_REPORT_STATUS.md` vs the authorization gaps in §3). They should move to `docs/history/` or be deleted.

### DOC-04 — Dead code in application modules — **Low**
`StudentFilterForm` and `StudentGroupEnrollmentForm` (`apps/students/forms.py:153-254`) are unused — views parse GET parameters by hand. `Student.phone_regex` (`models.py:93-96`) is unused. `school_name` is rendered as a `HiddenInput` with a placeholder (`forms.py:57`). Unused imports: `csrf_exempt` (`apps/students/api_views.py:9`, `apps/teachers/api_views.py:3`), `Case/When/IntegerField` (`apps/students/views.py:154`), `InvalidOperation` (`apps/payments/api_views.py:1`), `date`/`Count` (`apps/attendance/tasks.py:2,5`).

### DOC-05 — Dossier day names always render in English — **Low**
`apps/attendance/services.py:855` guards on `hasattr(group, 'SCHEDULE_DAY_CHOICES')`; the attribute is called `DAYS_CHOICES` (`apps/teachers/models.py:127`), so the branch never runs and the scanner shows "Saturday" instead of "السبت". A ready-made `DAY_NAMES_AR` map sits at `services.py:12-16` and is used correctly two lines below.

---

## Recommended order of work

**Immediately (hours):**
1. Rotate `SECRET_KEY`, untrack `.env`, set `DEBUG=False`, rotate the DB password — SEC-01/02/03.
2. Add role decorators to the money and student-state endpoints — AUTH-01/02/03/05/06.
3. Filter `notification_sent` in the notification task — BUG-05 (every hour it runs costs real WhatsApp spend).

**This week:**
4. Fix the rate-limit key so it reads `X-Forwarded-For` — AUTHN-01 (this is actively breaking daily use).
5. Escape `innerHTML` interpolation with the existing `escHtml()` — FE-01.
6. Pin `pytz` (or migrate to `zoneinfo`) — TZ-09.
7. Fix or remove the four dead features — BUG-01/02/03/04.
8. Wrap payment mutations in `transaction.atomic()` and log them — QUAL-04/05.

**This month:**
9. Replace `timezone.now().date()` with `timezone.localdate()` across the 16 sites — §6.
10. Resolve the dual schedule model — DATA-04 (root cause of six downstream bugs).
11. Turn off `continue-on-error` in CI and fix the `--deploy` job — OPS-09/10.
12. Add a payment receipt table with `created_by` — QUAL-06.
13. Paginate the list views and move bulk WhatsApp to Celery — PERF-01/02/03.
