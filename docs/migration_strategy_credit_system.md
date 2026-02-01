# Credit System Migration Strategy

## Overview
This document outlines the migration strategy from the old payment system to the new credit-based financial blocking system.

## Migration Steps

### 1. Backup Database
Before running any migrations, create a complete backup of your database:

```bash
# PostgreSQL
pg_dump -U username -d dbname > backup_before_migration.sql

# MySQL
mysqldump -u username -p dbname > backup_before_migration.sql

# SQLite
cp db.sqlite3 db.sqlite3.backup
```

### 2. Run Migrations
Run the Django migrations in order:

```bash
python manage.py makemigrations
python manage.py migrate
```

This will:
- Add new credit fields to `StudentGroupEnrollment`
- Create the `PaymentAuditLog` table
- Add indexes for better performance

### 3. Data Migration Script
After running migrations, you need to initialize the credit system data:

```python
# Create a management command: python manage.py migrate_credit_system
# Location: apps/payments/management/commands/migrate_credit_system.py

from django.core.management.base import BaseCommand
from django.db import transaction
from apps.students.models import StudentGroupEnrollment
from apps.payments.models import Payment
from django.utils import timezone
from datetime import datetime

class Command(BaseCommand):
    help = 'Migrate existing payment data to credit system'

    def handle(self, *args, **options):
        self.stdout.write('Starting credit system migration...')
        
        # Count total enrollments
        total = StudentGroupEnrollment.objects.count()
        self.stdout.write(f'Processing {total} enrollments...')
        
        with transaction.atomic():
            for i, enrollment in enumerate(StudentGroupEnrollment.objects.select_related('student', 'group').all()):
                # Determine if student is new or returning
                # Logic: If enrolled more than 2 months ago, consider as returning
                months_since_enrollment = (timezone.now() - enrollment.enrolled_at).days / 30
                
                if months_since_enrollment > 2:
                    enrollment.is_new_student = False
                    enrollment.credit_balance = 2  # Returning students get 2 sessions grace
                else:
                    enrollment.is_new_student = True
                    enrollment.credit_balance = 0  # New students must pay first
                
                # Get payment history for this enrollment
                payments = Payment.objects.filter(
                    student=enrollment.student,
                    group=enrollment.group
                ).order_by('month')
                
                # Calculate total sessions paid for
                total_sessions_paid = 0
                for payment in payments:
                    if payment.status == 'paid':
                        # Assume 4 sessions per month (adjust as needed)
                        total_sessions_paid += 4
                    elif payment.status == 'partial':
                        # Calculate partial sessions
                        ratio = payment.amount_paid / payment.amount_due
                        total_sessions_paid += int(4 * ratio)
                
                enrollment.sessions_paid_for = total_sessions_paid
                
                # Get attendance count from Attendance model
                from apps.attendance.models import Attendance
                sessions_attended = Attendance.objects.filter(
                    student=enrollment.student,
                    session__group=enrollment.group
                ).count()
                
                enrollment.sessions_attended = sessions_attended
                
                # Get last payment info
                last_payment = payments.filter(status__in=['paid', 'partial']).order_by('-payment_date').first()
                if last_payment:
                    enrollment.last_payment_date = last_payment.payment_date
                    enrollment.last_payment_amount = last_payment.amount_paid
                
                # Check if should be blocked
                debt = enrollment.sessions_attended - enrollment.sessions_paid_for
                remaining_credit = enrollment.credit_balance - debt
                
                if remaining_credit < 0:
                    enrollment.is_financially_blocked = True
                    enrollment.financial_block_reason = f'credit_exceeded_{abs(remaining_credit)}'
                elif enrollment.is_new_student and enrollment.sessions_paid_for == 0:
                    enrollment.is_financially_blocked = True
                    enrollment.financial_block_reason = 'new_student_no_payment'
                
                enrollment.save()
                
                # Progress indicator
                if (i + 1) % 100 == 0:
                    self.stdout.write(f'Processed {i + 1}/{total} enrollments...')
        
        self.stdout.write(self.style.SUCCESS('Credit system migration completed successfully!'))
```

### 4. Run Data Migration
Execute the management command:

```bash
python manage.py migrate_credit_system
```

### 5. Verification
After migration, verify the data:

```python
from apps.students.models import StudentGroupEnrollment
from apps.payments.services import CreditService

# Check credit status for all students
enrollments = StudentGroupEnrollment.objects.all()
for enrollment in enrollments:
    status = enrollment.get_credit_status()
    print(f"{enrollment.student.full_name} - {enrollment.group.group_name}")
    print(f"  New: {status['is_new_student']}, Credit: {status['credit_balance']}")
    print(f"  Attended: {status['sessions_attended']}, Paid: {status['sessions_paid_for']}")
    print(f"  Debt: {status['debt']}, Blocked: {status['is_blocked']}")
    print()
```

### 6. Rollback Plan (If Needed)
If issues arise, you can rollback:

```bash
# Rollback migrations
python manage.py migrate payments 0001_initial
python manage.py migrate students 0001_initial

# Restore database from backup
# PostgreSQL
psql -U username -d dbname < backup_before_migration.sql

# MySQL
mysql -u username -p dbname < backup_before_migration.sql

# SQLite
cp db.sqlite3.backup db.sqlite3
```

## Post-Migration Tasks

### 1. Review Financial Blocks
Check all financially blocked students:

```python
from apps.students.models import StudentGroupEnrollment

blocked = StudentGroupEnrollment.objects.filter(is_financially_blocked=True)
print(f"Total blocked students: {blocked.count()}")
for enrollment in blocked:
    print(f"- {enrollment.student.full_name}: {enrollment.financial_block_reason}")
```

### 2. Adjust Credit Balances (If Needed)
For students who should have different credit balances:

```python
from apps.payments.services import CreditService

# Example: Give a specific student extra credit
student = Student.objects.get(student_code='1234')
group = Group.objects.get(group_id=1)

CreditService.adjust_credit_balance(
    student=student,
    group=group,
    new_balance=5,  # 5 sessions grace period
    performed_by=None,  # System adjustment
    notes='Special case - extra credit granted'
)
```

### 3. Notify Users
Send notifications to parents about the new system:

```python
from apps.notifications.services import WhatsAppService

# Send bulk notification about new credit system
# (Implement based on your notification system)
```

## Testing Checklist

- [ ] New students cannot attend without payment
- [ ] Returning students can attend up to 2 sessions without payment
- [ ] 3rd unpaid session triggers automatic block
- [ ] Yellow screen displays correctly for financial blocks
- [ ] Credit balance updates correctly after payment
- [ ] Audit log records all changes
- [ ] Admin interface displays credit information correctly
- [ ] WhatsApp notifications sent for blocks and warnings

## Performance Considerations

The new system adds indexes for:
- `is_new_student`, `credit_balance` on `StudentGroupEnrollment`
- `is_financially_blocked` on `StudentGroupEnrollment`
- `student`, `created_at` on `PaymentAuditLog`
- `action`, `created_at` on `PaymentAuditLog`
- `performed_by` on `PaymentAuditLog`

These indexes ensure optimal query performance for the credit system.

## Support

If you encounter any issues during migration:
1. Check the logs in `logs/` directory
2. Review the audit log in admin panel
3. Run verification queries to check data integrity
4. Contact support with error messages and logs
