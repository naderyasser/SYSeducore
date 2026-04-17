# Rate Limiting Map — SYSeducore

Applied via `django-ratelimit` 4.1.0. Global toggle: `RATELIMIT_ENABLE` in `.env`.

## Rate-Limited Endpoints

| Endpoint | File | Rate | Key | Block | Reason |
|----------|------|------|-----|-------|--------|
| `POST /attendance/api/process-code/` | `apps/attendance/views.py:process_student_code` | 30/min | IP | Yes (429) | Scan endpoint — prevents brute-force of student codes |
| `POST /api/attendance/scan/` | `apps/attendance/api_views.py:process_scan` | 30/min | IP | Yes (429) | API scan endpoint — same protection as above |
| `GET/POST /accounts/login/` | `apps/accounts/views.py:login_view` | 5/min | IP | Yes (429) | Login — prevents credential stuffing |

## Endpoints NOT Rate-Limited (protected by other means)

| Endpoint | Protection | Why no rate limit |
|----------|-----------|-------------------|
| `POST /accounts/users/create/` | `@login_required` + `@admin_required` | Admin-only, behind auth |
| `POST /students/api/bulk-action/` | `@login_required` | Auth-gated, admin use only |
| `POST /payments/.../record/` | `@login_required` | Auth-gated, low volume |
| All report views | `@login_required` | Read-only, auth-gated |

## Frontend Handling

The scanner template (`templates/attendance/scanner.html`) checks for HTTP 429 responses
and displays an Arabic toast: "تم تجاوز الحد المسموح من الطلبات، انتظر قليلاً".

## Test Coverage

- `RATELIMIT_ENABLE = False` in `config/settings_test.py` to avoid interfering with normal tests
- `RateLimitScanEndpointTest` in `apps/attendance/tests.py` verifies decorator presence and normal access
