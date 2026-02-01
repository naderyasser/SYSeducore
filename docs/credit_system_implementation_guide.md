# Credit-Based Financial Blocking System - Implementation Guide

## Overview

This document provides a comprehensive guide to the credit-based financial blocking system implemented for the Django educational center. The system differentiates between new and returning students with different payment rules.

## System Architecture

### Core Components

1. **StudentGroupEnrollment Model** ([`apps/students/models.py`](apps/students/models.py:67))
   - Extended with credit tracking fields
   - Methods for credit status checking

2. **CreditService** ([`apps/payments/services.py`](apps/payments/services.py:11))
   - Central service for credit management
   - Transaction-safe operations

3. **PaymentAuditLog Model** ([`apps/payments/models.py`](apps/payments/models.py:11))
   - Audit trail for all financial changes
   - Complete change history

4. **AttendanceService Integration** ([`apps/attendance/services.py`](apps/attendance/services.py:304))
   - Financial status checking before attendance
   - Automatic credit updates

## Credit System Rules

### New Students
- **Credit Balance**: 0 sessions
- **Rule**: Must pay before attending ANY session
- **Block**: Yellow screen on first attendance attempt without payment

### Returning Students
- **Credit Balance**: 2 sessions (grace period)
- **Rule**: Can attend up to 2 sessions without payment
- **Block**: Yellow screen on 3rd unpaid session

### Blocking Rules
1. New student + no payment = 🟡 YELLOW block "Payment Required"
2. Old student + debt > 2 sessions = 🟡 YELLOW block "Outstanding Payment"
3. Any student with active payment = 🟢 GREEN allowed

## Database Schema

### StudentGroupEnrollment Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `is_new_student` | Boolean | True | New vs returning student |
| `credit_balance` | Integer | 0 | Sessions allowed without payment |
| `sessions_attended` | Integer | 0 | Counter for attended sessions |
| `sessions_paid_for` | Integer | 0 | Counter for paid sessions |
| `last_payment_date` | DateTime | Null | Date of last payment |
| `last_payment_amount` | Decimal | Null | Amount of last payment |
| `is_financially_blocked` | Boolean | False | Auto-block flag |
| `financial_block_reason` | String | Empty | Reason for block |

### PaymentAuditLog Fields

| Field | Type | Description |
|-------|------|-------------|
| `action` | Choice | Type of action performed |
| `old_value` | JSON | Previous state |
| `new_value` | JSON | New state |
| `amount` | Decimal | Payment amount |
| `sessions_count` | Integer | Number of sessions |
| `performed_by` | Foreign Key | User who made change |
| `ip_address` | IP Address | Client IP |

## API Usage

### Checking Credit Status

```python
from apps.payments.services import CreditService

# Check if student can attend
result = CreditService.check_credit_status(student, group)

if result['allowed']:
    print("Student can attend")
else:
    print(f"Blocked: {result['message']}")
```

### Recording Payment

```python
from apps.payments.services import CreditService

# Record payment and update credit
result = CreditService.record_payment_and_update_credit(
    student=student,
    group=group,
    amount=100.00,
    sessions_count=4,
    performed_by=request.user,
    notes="Monthly payment"
)
```

### Manual Credit Adjustment

```python
# Adjust credit balance (admin only)
result = CreditService.adjust_credit_balance(
    student=student,
    group=group,
    new_balance=5,
    performed_by=request.user,
    notes="Special case - extra credit"
)
```

### Getting Credit Report

```python
from apps.payments.services import CreditService

# Get comprehensive report
report = CreditService.get_credit_report(group=group)

print(f"Total enrollments: {report['total_enrollments']}")
print(f"New students: {report['new_students']}")
print(f"With debt: {report['with_debt']}")
```

## Admin Interface

### StudentGroupEnrollment Admin

**Location**: `/admin/students/studentgroupenrollment/`

**Features**:
- View credit status for all enrollments
- Quick edit credit balance and student type
- Bulk actions for credit management

**Bulk Actions**:
- 🆕 Mark as New Student (credit = 0)
- 🔄 Mark as Returning Student (credit = 2)
- 🔓 Clear Financial Block
- 🔄 Reset Credit Balance

**List Display**:
- Colored credit status badges
- Sessions attended vs paid
- Block status indicator

### PaymentAuditLog Admin

**Location**: `/admin/payments/paymentauditlog/`

**Features**:
- Complete audit trail
- Filter by action type
- View old/new values
- Track who made changes

**Read-Only**: Logs cannot be modified (security)

## WhatsApp Notifications

### Notification Types

1. **Payment Block - New Student**
   - Triggered when new student tries to attend without payment
   - Template: `payment_block_new`

2. **Payment Block - Debt Exceeded**
   - Triggered when debt > 2 sessions
   - Template: `payment_block_debt`

3. **Credit Warning**
   - Sent when 1 session remaining
   - Template: `credit_warning`

4. **Final Warning**
   - Sent on 2nd unpaid session
   - Template: `credit_final_warning`

### Template Location

[`apps/payments/whatsapp_templates.py`](apps/payments/whatsapp_templates.py:1)

## Migration Steps

### 1. Backup Database
```bash
# PostgreSQL
pg_dump -U username -d dbname > backup.sql

# MySQL
mysqldump -u username -p dbname > backup.sql
```

### 2. Run Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### 3. Run Data Migration
```bash
# Dry run first (recommended)
python manage.py migrate_credit_system --dry-run

# Actual migration
python manage.py migrate_credit_system
```

### 4. Verify Data
```python
from apps.students.models import StudentGroupEnrollment

# Check migration results
blocked = StudentGroupEnrollment.objects.filter(is_financially_blocked=True)
print(f"Blocked students: {blocked.count()}")
```

## Transaction Handling

All credit operations use Django transactions:

```python
@transaction.atomic
def record_payment_and_update_credit(...):
    # Multiple operations in single transaction
    # All succeed or all fail
```

**Race Condition Prevention**:
```python
enrollment = StudentGroupEnrollment.objects.select_for_update().get(...)
# Locks row until transaction completes
```

## Testing Checklist

- [ ] New student blocked without payment
- [ ] Returning student can attend 2 sessions unpaid
- [ ] 3rd session triggers block
- [ ] Yellow screen displays correctly
- [ ] Credit updates after payment
- [ ] Audit log records changes
- [ ] WhatsApp notifications sent
- [ ] Admin interface works
- [ ] Bulk operations work
- [ ] Migration completes successfully

## Troubleshooting

### Issue: Students incorrectly blocked
**Solution**: Check credit balance and debt calculation
```python
enrollment = StudentGroupEnrollment.objects.get(student=student, group=group)
print(enrollment.get_credit_status())
```

### Issue: Payments not updating credit
**Solution**: Ensure `CreditService.record_payment_and_update_credit()` is called

### Issue: Missing notifications
**Solution**: Check WhatsApp service configuration and templates

### Issue: Migration fails
**Solution**: 
1. Check database backup
2. Review error logs
3. Run with `--dry-run` first

## Performance Considerations

### Indexes Added
- `is_new_student`, `credit_balance` on StudentGroupEnrollment
- `is_financially_blocked` on StudentGroupEnrollment
- `student`, `created_at` on PaymentAuditLog
- `action`, `created_at` on PaymentAuditLog

### Query Optimization
- Use `select_related()` for foreign keys
- Use `prefetch_related()` for many-to-many
- Use `select_for_update()` for transaction safety

## Security Notes

1. **Audit Log**: All financial changes are logged
2. **Transaction Safety**: Operations use atomic transactions
3. **Row Locking**: Prevents race conditions
4. **Admin Only**: Credit adjustments require admin permission
5. **Read-Only Logs**: Audit logs cannot be modified

## Future Enhancements

Potential improvements:
1. Automated payment reminders via email/SMS
2. Parent portal for viewing credit status
3. Payment gateway integration
4. Custom credit packages
5. Refund handling
6. Session credit rollover

## Support

For issues or questions:
1. Check logs in `logs/` directory
2. Review audit log in admin panel
3. Run verification queries
4. Contact development team

## Files Modified/Created

### Modified Files
- [`apps/students/models.py`](apps/students/models.py:67) - Credit fields added
- [`apps/payments/models.py`](apps/payments/models.py:11) - PaymentAuditLog added
- [`apps/payments/services.py`](apps/payments/services.py:11) - CreditService added
- [`apps/attendance/services.py`](apps/attendance/services.py:304) - Financial check updated
- [`apps/students/admin.py`](apps/students/admin.py:65) - Credit admin interface
- [`apps/payments/admin.py`](apps/payments/admin.py:5) - Audit log admin
- [`templates/attendance/partials/kiosk_yellow.html`](templates/attendance/partials/kiosk_yellow.html:1) - Credit info display

### New Files
- [`apps/payments/whatsapp_templates.py`](apps/payments/whatsapp_templates.py:1) - Credit notifications
- [`apps/students/migrations/0002_add_credit_system_fields.py`](apps/students/migrations/0002_add_credit_system_fields.py:1) - Credit fields migration
- [`apps/payments/migrations/0002_add_payment_audit_log.py`](apps/payments/migrations/0002_add_payment_audit_log.py:1) - Audit log migration
- [`apps/payments/management/commands/migrate_credit_system.py`](apps/payments/management/commands/migrate_credit_system.py:1) - Data migration command
- [`docs/migration_strategy_credit_system.md`](docs/migration_strategy_credit_system.md:1) - Migration guide
