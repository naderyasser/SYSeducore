"""
Django management command to prepare database for production.
Deletes all test data while preserving admin/superuser accounts.

Usage:
    python manage.py prepare_production
    python manage.py prepare_production --confirm
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.models import Teacher, Group, Room, Subject
from apps.attendance.models import Session, Attendance, ActivityLog
from apps.payments.models import Payment
from apps.notifications.models import WhatsAppMessage, MessageTemplate

User = get_user_model()


class Command(BaseCommand):
    help = 'Prepare database for production by removing all test data (preserves admin accounts)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm deletion without prompting',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(self.style.WARNING(
                '\n⚠️  WARNING: This will DELETE ALL test data!\n'
                'The following will be removed:\n'
                '  - All Students\n'
                '  - All Teachers\n'
                '  - All Groups\n'
                '  - All Attendance records\n'
                '  - All Payment records\n'
                '  - All Sessions\n'
                '  - All WhatsApp messages\n'
                '  - All Rooms and Subjects\n\n'
                '✅ Admin/Superuser accounts will be PRESERVED\n'
            ))
            
            confirm = input('Type "DELETE ALL DATA" to proceed: ')
            if confirm != 'DELETE ALL DATA':
                self.stdout.write(self.style.ERROR('Aborted.'))
                return

        self.stdout.write(self.style.WARNING('\n🔄 Starting data cleanup...\n'))

        try:
            with transaction.atomic():
                # Count before deletion
                counts = {
                    'students': Student.objects.count(),
                    'teachers': Teacher.objects.count(),
                    'groups': Group.objects.count(),
                    'enrollments': StudentGroupEnrollment.objects.count(),
                    'sessions': Session.objects.count(),
                    'attendance': Attendance.objects.count(),
                    'payments': Payment.objects.count(),
                    'rooms': Room.objects.count(),
                    'subjects': Subject.objects.count(),
                    'messages': WhatsAppMessage.objects.count(),
                    'templates': MessageTemplate.objects.count(),
                    'activity_logs': ActivityLog.objects.count(),
                }

                self.stdout.write('📊 Current counts:')
                for model, count in counts.items():
                    self.stdout.write(f'  - {model}: {count}')

                # Delete in correct order (respecting foreign keys)
                self.stdout.write('\n🗑️  Deleting data...\n')

                # 1. Delete attendance and activity logs
                deleted = ActivityLog.objects.all().delete()[0]
                self.stdout.write(f'  ✓ Deleted {deleted} activity logs')

                deleted = Attendance.objects.all().delete()[0]
                self.stdout.write(f'  ✓ Deleted {deleted} attendance records')

                deleted = Session.objects.all().delete()[0]
                self.stdout.write(f'  ✓ Deleted {deleted} sessions')

                # 2. Delete payments
                deleted = Payment.objects.all().delete()[0]
                self.stdout.write(f'  ✓ Deleted {deleted} payments')

                # 3. Delete notifications
                deleted = WhatsAppMessage.objects.all().delete()[0]
                self.stdout.write(f'  ✓ Deleted {deleted} WhatsApp messages')

                deleted = MessageTemplate.objects.all().delete()[0]
                self.stdout.write(f'  ✓ Deleted {deleted} message templates')

                # 4. Delete enrollments
                deleted = StudentGroupEnrollment.objects.all().delete()[0]
                self.stdout.write(f'  ✓ Deleted {deleted} student enrollments')

                # 5. Delete groups
                deleted = Group.objects.all().delete()[0]
                self.stdout.write(f'  ✓ Deleted {deleted} groups')

                # 6. Delete students and teachers
                deleted = Student.objects.all().delete()[0]
                self.stdout.write(f'  ✓ Deleted {deleted} students')

                deleted = Teacher.objects.all().delete()[0]
                self.stdout.write(f'  ✓ Deleted {deleted} teachers')

                # 7. Delete rooms and subjects
                deleted = Room.objects.all().delete()[0]
                self.stdout.write(f'  ✓ Deleted {deleted} rooms')

                deleted = Subject.objects.all().delete()[0]
                self.stdout.write(f'  ✓ Deleted {deleted} subjects')

                # Verify admin accounts are preserved
                admin_count = User.objects.filter(is_superuser=True).count()
                self.stdout.write(f'\n✅ Preserved {admin_count} admin account(s)')

                self.stdout.write(self.style.SUCCESS(
                    '\n✅ Database cleanup completed successfully!\n'
                    'The database is now ready for production use.\n'
                ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Error during cleanup: {str(e)}\n'))
            raise
