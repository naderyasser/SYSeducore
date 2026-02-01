from django.core.management.base import BaseCommand
from django.db import transaction
from apps.students.models import StudentGroupEnrollment
from apps.payments.models import Payment
from django.utils import timezone
from datetime import datetime


class Command(BaseCommand):
    help = 'Migrate existing payment data to credit system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Show what would be migrated without actually migrating',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        self.stdout.write('Starting credit system migration...')
        
        # Count total enrollments
        total = StudentGroupEnrollment.objects.count()
        self.stdout.write(f'Processing {total} enrollments...')
        
        with transaction.atomic():
            # Use savepoint for dry run
            sid = transaction.savepoint()
            
            try:
                for i, enrollment in enumerate(StudentGroupEnrollment.objects.select_related('student', 'group').all()):
                    # Store old values for reporting
                    old_values = {
                        'is_new_student': enrollment.is_new_student,
                        'credit_balance': enrollment.credit_balance,
                        'sessions_paid_for': enrollment.sessions_paid_for,
                        'sessions_attended': enrollment.sessions_attended,
                    }
                    
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
                            ratio = payment.amount_paid / payment.amount_due if payment.amount_due > 0 else 0
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
                    elif enrollment.is_new_student and enrollment.sessions_paid_for == 0 and sessions_attended > 0:
                        enrollment.is_financially_blocked = True
                        enrollment.financial_block_reason = 'new_student_no_payment'
                    else:
                        enrollment.is_financially_blocked = False
                        enrollment.financial_block_reason = ''
                    
                    if not dry_run:
                        enrollment.save()
                    
                    # Progress indicator
                    if (i + 1) % 100 == 0:
                        self.stdout.write(f'Processed {i + 1}/{total} enrollments...')
                    
                    # Show changes for first 10 enrollments
                    if i < 10:
                        self.stdout.write(f'\n{enrollment.student.full_name} - {enrollment.group.group_name}:')
                        self.stdout.write(f'  Old: New={old_values["is_new_student"]}, Credit={old_values["credit_balance"]}, Paid={old_values["sessions_paid_for"]}, Attended={old_values["sessions_attended"]}')
                        self.stdout.write(f'  New: New={enrollment.is_new_student}, Credit={enrollment.credit_balance}, Paid={enrollment.sessions_paid_for}, Attended={enrollment.sessions_attended}')
                        self.stdout.write(f'  Blocked: {enrollment.is_financially_blocked} ({enrollment.financial_block_reason})')
                
                if dry_run:
                    self.stdout.write(self.style.WARNING('\nDRY RUN COMPLETE - Rolling back changes'))
                    transaction.savepoint_rollback(sid)
                else:
                    self.stdout.write(self.style.SUCCESS('\nCredit system migration completed successfully!'))
                    
                    # Show summary
                    new_students = StudentGroupEnrollment.objects.filter(is_new_student=True).count()
                    returning_students = StudentGroupEnrollment.objects.filter(is_new_student=False).count()
                    blocked = StudentGroupEnrollment.objects.filter(is_financially_blocked=True).count()
                    
                    self.stdout.write('\nSummary:')
                    self.stdout.write(f'  New students: {new_students}')
                    self.stdout.write(f'  Returning students: {returning_students}')
                    self.stdout.write(f'  Financially blocked: {blocked}')
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'\nMigration failed: {str(e)}'))
                transaction.savepoint_rollback(sid)
                raise
