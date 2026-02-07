"""
Management command to seed the database with Egyptian demo data.
"""
import random
from datetime import datetime, timedelta, date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.teachers.models import Teacher, Group, Room
from apps.students.models import Student, StudentGroupEnrollment
from apps.attendance.models import Session, Attendance
from apps.payments.models import Payment


class Command(BaseCommand):
    help = 'Seed the database with Egyptian demo data'

    # Egyptian names (realistic)
    MALE_FIRST_NAMES = [
        'محمد', 'أحمد', 'محمود', 'عمر', 'عبدالله', 'عبدالرحمن', 'يوسف', 'إبراهيم',
        'على', 'حسن', 'حسين', 'كريم', 'مصطفى', 'خالد', 'طارق', 'سامح', 'وائل',
        'أشرف', 'مجدى', 'سيد', 'إسلام', 'أيمن', 'باسم', 'تامر', 'جمال', 'رامي',
        'زياد', 'سامي', 'شريف', 'صابر', 'ضياء', 'طاهر', 'عادل', 'فادي', 'فتحي',
        'فهمي', 'قاسم', 'كمال', 'لؤي', 'مازن', 'مختار', 'مدحت', 'مراد', 'ممدوح',
        'منير', 'نادر', 'ناجي', 'نبيل', 'نصر', 'هاني', 'هشام', 'وليد', 'ياسر'
    ]

    FEMALE_FIRST_NAMES = [
        'فاطمة', 'آية', 'مريم', 'نور', 'سلمى', 'حنين', 'ملك', 'جنى', 'سارة',
        'نورهان', 'ريماس', 'آلاء', 'رحمة', 'هاجر', 'شهد', 'أسماء', 'رنا', 'دعاء',
        'إيمان', 'حبيبة', 'خلود', 'رحاب', 'زينب', 'سمر', 'شيرين', 'صافية',
        'عفاف', 'غادة', 'فريدة', 'قمر', 'كريمة', 'لمياء', 'ماجدة', 'مديحة',
        'مروة', 'ميساء', 'نادية', 'نهى', 'هالة', 'هبة', 'هدى', 'هند', 'وفاء',
        'ياسمين', 'إسراء', 'استر', 'باسمة', 'تسنيم', 'ثريا', 'جاسمين', 'جمانة'
    ]

    LAST_NAMES = [
        'أحمد', 'محمد', 'محمود', 'عبدالله', 'عبدالرحمن', 'عبدالعزيز', 'عبدالفتاح',
        'عبدالهادي', 'عبدالكريم', 'عبدالغفور', 'علي', 'حسن', 'حسين', 'إبراهيم',
        'عمر', 'عثمان', 'السيد', 'الشريف', 'فؤاد', 'فهمي', 'كمال', 'لطفي',
        'ناجي', 'نصر', 'هاشم', 'يوسف', 'الطاهر', 'الطيب', 'السقا', 'الكومي',
        'المنياوي', 'السوهاجي', 'القناوي', 'الأقصري', 'الأسيوطي', 'البحيري',
        'الإسكندراني', 'القاهري', 'الجيزاوي', 'الشرقاوي', 'الغرباوي', 'الدقهلي',
        'المنوفي', 'الشرابي', 'السكندري', 'المحمدي', 'العريشي', 'السيناوي'
    ]

    SUBJECTS = [
        'رياضيات', 'لغة عربية', 'لغة إنجليزية', 'فيزياء', 'كيمياء',
        'أحياء', 'تاريخ', 'جغرافيا', 'علوم', 'تربية دينية'
    ]

    GRADES = [
        'الصف الأول الإعدادي', 'الصف الثاني الإعدادي', 'الصف الثالث الإعدادي',
        'الصف الأول الثانوي', 'الصف الثاني الثانوي', 'الصف الثالث الثانوي'
    ]

    ROOMS = [
        'قاعة 1', 'قاعة 2', 'قاعة 3', 'قاعة 4', 'قاعة 5',
        'المعمل 1', 'المعمل 2', 'القاعة الكبيرة'
    ]

    DAYS = [
        ('Saturday', 'السبت'), ('Sunday', 'الأحد'), ('Monday', 'الاثنين'),
        ('Tuesday', 'الثلاثاء'), ('Wednesday', 'الأربعاء'), ('Thursday', 'الخميس')
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            '--teachers', type=int, default=6,
            help='Number of teachers to create (default: 6)'
        )
        parser.add_argument(
            '--students', type=int, default=60,
            help='Number of students to create (default: 60)'
        )
        parser.add_argument(
            '--groups', type=int, default=10,
            help='Number of groups to create (default: 10)'
        )

    def generate_egyptian_phone(self):
        """Generate a realistic Egyptian phone number."""
        prefixes = ['010', '011', '012', '015']
        prefix = random.choice(prefixes)
        number = ''.join([str(random.randint(0, 9)) for _ in range(8)])
        return f"{prefix}{number}"

    def generate_full_name(self, gender='male'):
        """Generate a realistic Egyptian full name."""
        if gender == 'male':
            first_name = random.choice(self.MALE_FIRST_NAMES)
        else:
            first_name = random.choice(self.FEMALE_FIRST_NAMES)
        
        # Sometimes add father's name
        if random.random() > 0.3:
            father_name = random.choice(self.MALE_FIRST_NAMES)
            first_name = f"{first_name} {father_name}"
        
        last_name = random.choice(self.LAST_NAMES)
        return f"{first_name} {last_name}"

    def create_rooms(self):
        """Create rooms."""
        self.stdout.write('Creating rooms...')
        rooms = []
        for room_name in self.ROOMS:
            room, created = Room.objects.get_or_create(
                name=room_name,
                defaults={'capacity': random.choice([20, 25, 30, 35, 40])}
            )
            rooms.append(room)
            if created:
                self.stdout.write(f'  Created room: {room_name}')
        return rooms

    def create_teachers(self, count):
        """Create teachers with Egyptian names."""
        self.stdout.write(f'Creating {count} teachers...')
        teachers = []
        
        specializations = random.sample(self.SUBJECTS, min(count, len(self.SUBJECTS)))
        
        for i in range(count):
            full_name = self.generate_full_name('male')
            specialization = specializations[i % len(specializations)]
            
            teacher, created = Teacher.objects.get_or_create(
                email=f"teacher{i+1}@educore.com",
                defaults={
                    'full_name': full_name,
                    'phone': self.generate_egyptian_phone(),
                    'specialization': specialization,
                    'hire_date': date(2020 + random.randint(0, 4), random.randint(1, 12), 1)
                }
            )
            teachers.append(teacher)
            if created:
                self.stdout.write(f'  Created teacher: {full_name} ({specialization})')
        
        return teachers

    def create_groups(self, count, teachers, rooms):
        """Create groups/classes."""
        self.stdout.write(f'Creating {count} groups...')
        groups = []
        
        # Generate unique schedules
        schedules = []
        for day_code, day_name in self.DAYS:
            for hour in [16, 17, 18, 19]:
                for room in rooms:
                    schedules.append({
                        'day': day_code,
                        'day_name': day_name,
                        'hour': hour,
                        'room': room
                    })
        
        random.shuffle(schedules)
        
        for i in range(min(count, len(schedules))):
            teacher = teachers[i % len(teachers)]
            schedule = schedules[i]
            subject = teacher.specialization
            grade = random.choice(self.GRADES)
            
            group_name = f"{grade} - {subject}"
            
            from datetime import time
            start_time = time(schedule['hour'], 0)
            
            group, created = Group.objects.get_or_create(
                group_name=group_name,
                teacher=teacher,
                defaults={
                    'room': schedule['room'],
                    'schedule_day': schedule['day'],
                    'schedule_time': start_time,
                    'standard_fee': Decimal(random.choice([250, 300, 350, 400])),
                    'center_percentage': Decimal(random.choice([25, 30, 35]))
                }
            )
            groups.append(group)
            if created:
                self.stdout.write(f'  Created group: {group_name} ({schedule["day_name"]} {schedule["hour"]}:00)')
        
        return groups

    def create_students(self, count, groups):
        """Create students with Egyptian names."""
        self.stdout.write(f'Creating {count} students...')
        students = []
        
        for i in range(count):
            gender = random.choice(['male', 'female'])
            full_name = self.generate_full_name(gender)
            
            # Generate unique student code
            student_code = f"{1001 + i}"
            
            student, created = Student.objects.get_or_create(
                student_code=student_code,
                defaults={
                    'full_name': full_name,
                    'parent_phone': self.generate_egyptian_phone()
                }
            )
            
            # Assign to 1-3 random groups with financial status
            num_groups = random.randint(1, min(3, len(groups)))
            assigned_groups = random.sample(groups, num_groups)
            
            for group in assigned_groups:
                financial_status = random.choices(
                    ['normal', 'symbolic', 'exempt'],
                    weights=[75, 20, 5],
                    k=1
                )[0]
                
                custom_fee = None
                if financial_status == 'symbolic':
                    custom_fee = Decimal(random.choice([50, 75, 100]))
                
                StudentGroupEnrollment.objects.get_or_create(
                    student=student,
                    group=group,
                    defaults={
                        'financial_status': financial_status,
                        'custom_fee': custom_fee
                    }
                )
            
            students.append(student)
            if created:
                self.stdout.write(f'  Created student: {full_name} (Code: {student_code})')
        
        return students

    def create_sessions(self, groups, days_back=30):
        """Create past sessions for attendance tracking."""
        self.stdout.write(f'Creating sessions for the past {days_back} days...')
        sessions = []
        
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days_back)
        
        day_mapping = {
            'Saturday': 5, 'Sunday': 6, 'Monday': 0, 'Tuesday': 1,
            'Wednesday': 2, 'Thursday': 3, 'Friday': 4
        }
        
        for group in groups:
            target_weekday = day_mapping.get(group.schedule_day, 0)
            
            current_date = start_date
            while current_date <= end_date:
                if current_date.weekday() == target_weekday:
                    # 10% chance of cancellation
                    is_cancelled = random.random() < 0.1
                    
                    session, created = Session.objects.get_or_create(
                        group=group,
                        session_date=current_date,
                        defaults={
                            'teacher_attended': not is_cancelled and random.random() < 0.95,
                            'is_cancelled': is_cancelled,
                            'cancellation_reason': 'ظروف طارئة' if is_cancelled else ''
                        }
                    )
                    sessions.append(session)
                
                current_date += timedelta(days=1)
        
        self.stdout.write(f'  Created {len(sessions)} sessions')
        return sessions

    def create_attendance(self, sessions):
        """Create attendance records."""
        self.stdout.write('Creating attendance records...')
        attendance_count = 0
        
        for session in sessions:
            if session.is_cancelled:
                continue
            
            # Get enrolled students through the enrollment model
            enrollments = StudentGroupEnrollment.objects.filter(
                group=session.group,
                is_active=True
            )
            
            for enrollment in enrollments:
                student = enrollment.student
                
                # Determine attendance status (85% present, 10% absent, 5% late)
                rand = random.random()
                if rand < 0.85:
                    status = 'present'
                elif rand < 0.95:
                    status = 'absent'
                else:
                    status = 'late'
                
                # Generate scan time
                scan_time = timezone.make_aware(datetime.combine(
                    session.session_date,
                    session.group.schedule_time
                ))
                
                if status == 'late':
                    scan_time += timedelta(minutes=random.randint(5, 20))
                
                attendance, created = Attendance.objects.get_or_create(
                    session=session,
                    student=student,
                    defaults={
                        'status': status,
                        'scan_time': scan_time,
                        'rejection_reason': ''
                    }
                )
                if created:
                    attendance_count += 1
        
        self.stdout.write(f'  Created {attendance_count} attendance records')

    def create_payments(self, students, months_back=3):
        """Create payment records."""
        self.stdout.write(f'Creating payments for the past {months_back} months...')
        payment_count = 0
        
        current_date = timezone.now().date()
        
        for student in students:
            # Get student's enrollments
            enrollments = StudentGroupEnrollment.objects.filter(
                student=student,
                is_active=True
            )
            
            for enrollment in enrollments:
                group = enrollment.group
                
                # Calculate fee based on financial status
                if enrollment.financial_status == 'exempt':
                    amount_due = Decimal('0')
                elif enrollment.financial_status == 'symbolic':
                    amount_due = enrollment.custom_fee or Decimal('100')
                else:
                    amount_due = group.standard_fee
                
                # Create payments for past months
                for i in range(months_back):
                    month_date = current_date - timedelta(days=30*i)
                    # First day of month
                    month_date = month_date.replace(day=1)
                    
                    # Determine payment status
                    if amount_due == 0:
                        status = 'paid'
                        amount_paid = Decimal('0')
                    else:
                        status = random.choices(
                            ['paid', 'partial', 'unpaid'],
                            weights=[80, 15, 5],
                            k=1
                        )[0]
                        
                        if status == 'paid':
                            amount_paid = amount_due
                        elif status == 'partial':
                            amount_paid = amount_due * Decimal('0.5')
                        else:
                            amount_paid = Decimal('0')
                    
                    payment, created = Payment.objects.get_or_create(
                        student=student,
                        group=group,
                        month=month_date,
                        defaults={
                            'amount_due': amount_due,
                            'amount_paid': amount_paid,
                            'status': status,
                            'payment_date': timezone.now() if amount_paid > 0 else None,
                            'notes': ''
                        }
                    )
                    if created:
                        payment_count += 1
        
        self.stdout.write(f'  Created {payment_count} payment records')

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Seeding Egyptian Demo Data'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        
        # Create data
        rooms = self.create_rooms()
        teachers = self.create_teachers(options['teachers'])
        groups = self.create_groups(options['groups'], teachers, rooms)
        students = self.create_students(options['students'], groups)
        sessions = self.create_sessions(groups)
        self.create_attendance(sessions)
        self.create_payments(students)
        
        # Summary
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Demo Data Summary:'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f"  Rooms: {Room.objects.count()}")
        self.stdout.write(f"  Teachers: {Teacher.objects.count()}")
        self.stdout.write(f"  Groups: {Group.objects.count()}")
        self.stdout.write(f"  Students: {Student.objects.count()}")
        self.stdout.write(f"  Enrollments: {StudentGroupEnrollment.objects.count()}")
        self.stdout.write(f"  Sessions: {Session.objects.count()}")
        self.stdout.write(f"  Attendance Records: {Attendance.objects.count()}")
        self.stdout.write(f"  Payments: {Payment.objects.count()}")
        self.stdout.write(self.style.SUCCESS('=' * 60))
        
        self.stdout.write(self.style.SUCCESS('\nLogin Credentials:'))
        self.stdout.write('  Admin: admin / admin123')
        self.stdout.write(self.style.SUCCESS('=' * 60))
