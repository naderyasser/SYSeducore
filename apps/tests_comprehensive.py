"""
Comprehensive Unit Tests for SYSeducore
اختبارات شاملة للنظام - فحص جميع الصفحات والـ APIs
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, '/root/.gemini/antigravity/scratch/SYSeducore')
django.setup()

# Add testserver to allowed hosts for testing
from django.conf import settings
settings.ALLOWED_HOSTS.append('testserver')

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse, NoReverseMatch
from apps.teachers.models import Teacher, Group, Room, Subject
from apps.students.models import Student, StudentGroupEnrollment
from apps.attendance.models import Session, Attendance
from apps.payments.models import Payment
from apps.notifications.models import WhatsAppMessage

User = get_user_model()


class PageTestResult:
    """Store test results"""
    def __init__(self):
        self.results = []

    def add(self, url, status, has_data, message=""):
        self.results.append({
            'url': url,
            'status': status,
            'has_data': has_data,
            'message': message
        })

    def print_report(self):
        print("\n" + "="*80)
        print("📊 تقرير اختبار الصفحات الشامل")
        print("="*80)

        passed = [r for r in self.results if r['status'] == 200]
        failed = [r for r in self.results if r['status'] != 200]

        print(f"\n✅ الصفحات الناجحة: {len(passed)}")
        print(f"❌ الصفحات الفاشلة: {len(failed)}")
        print(f"📄 إجمالي الصفحات: {len(self.results)}")

        if failed:
            print("\n" + "-"*40)
            print("❌ الصفحات الفاشلة:")
            print("-"*40)
            for r in failed:
                print(f"  [{r['status']}] {r['url']}")
                if r['message']:
                    print(f"       → {r['message']}")

        print("\n" + "-"*40)
        print("📋 تفاصيل كل الصفحات:")
        print("-"*40)
        for r in self.results:
            status_icon = "✅" if r['status'] == 200 else "❌"
            data_icon = "📦" if r['has_data'] else "📭"
            print(f"  {status_icon} [{r['status']}] {data_icon} {r['url']}")

        print("\n" + "="*80)
        return len(failed) == 0


def run_comprehensive_tests():
    """Run all page tests"""
    results = PageTestResult()
    client = Client()

    # Create test user and login
    print("\n🔐 إنشاء مستخدم تجريبي...")
    user, created = User.objects.get_or_create(
        username='test_admin',
        defaults={
            'email': 'test@test.com',
            'is_staff': True,
            'is_superuser': True,
            'is_active': True,
        }
    )
    if created:
        user.set_password('testpass123')
        user.save()

    # Login
    client.login(username='test_admin', password='testpass123')
    print("✅ تم تسجيل الدخول")

    # Create test data if not exists
    print("\n📦 التحقق من البيانات التجريبية...")

    # Teacher
    from datetime import date
    teacher = Teacher.objects.filter(is_active=True).first()
    if not teacher:
        teacher = Teacher.objects.create(
            full_name='مدرس تجريبي',
            phone='01234567890',
            specialization='رياضيات',
            hire_date=date.today(),
            is_active=True
        )
    print(f"  - المدرسين: {Teacher.objects.count()}")

    # Room
    room = Room.objects.filter(is_active=True).first()
    if not room:
        room = Room.objects.create(name='قاعة تجريبية', capacity=30, is_active=True)
    print(f"  - القاعات: {Room.objects.count()}")

    # Group
    group = Group.objects.filter(is_active=True).first()
    if not group:
        group = Group.objects.create(
            group_name='مجموعة تجريبية للاختبار',
            teacher=teacher,
            room=room,
            schedule_day='Saturday',
            schedule_time='14:00',
            standard_fee=200,
            is_active=True
        )
    print(f"  - المجموعات: {Group.objects.count()}")

    # Student
    student = Student.objects.filter(is_active=True).first()
    if not student:
        student = Student.objects.create(
            full_name='طالب تجريبي',
            phone='01111111111',
            student_code='TEST001',
            is_active=True
        )
    print(f"  - الطلاب: {Student.objects.count()}")

    # ===== TEST ALL PAGES =====
    print("\n🧪 بدء اختبار الصفحات...")

    # Define all URLs to test
    urls_to_test = [
        # Dashboard & Reports
        ('/', 'الصفحة الرئيسية'),
        ('/accounts/login/', 'صفحة تسجيل الدخول'),

        # Teachers App
        ('/teachers/', 'قائمة المدرسين'),
        ('/teachers/create/', 'إضافة مدرس'),
        (f'/teachers/{teacher.teacher_id}/', 'تفاصيل مدرس'),
        (f'/teachers/{teacher.teacher_id}/edit/', 'تعديل مدرس'),

        # Rooms
        ('/teachers/rooms/', 'قائمة القاعات'),
        ('/teachers/rooms/create/', 'إضافة قاعة'),
        (f'/teachers/rooms/{room.room_id}/', 'تفاصيل قاعة'),

        # Groups
        ('/teachers/groups/', 'قائمة المجموعات'),
        ('/teachers/groups/create/', 'إضافة مجموعة'),
        (f'/teachers/groups/{group.group_id}/', 'تفاصيل مجموعة'),
        (f'/teachers/groups/{group.group_id}/edit/', 'تعديل مجموعة'),

        # Subjects
        ('/teachers/subjects/', 'قائمة المواد'),
        ('/teachers/subjects/create/', 'إضافة مادة'),

        # Students App
        ('/students/', 'قائمة الطلاب'),
        ('/students/create/', 'إضافة طالب'),
        (f'/students/{student.student_id}/', 'تفاصيل طالب'),
        (f'/students/{student.student_id}/update/', 'تعديل طالب'),

        # Attendance
        ('/attendance/scanner/', 'الماسح الضوئي'),

        # Payments
        ('/payments/', 'قائمة المدفوعات'),
        (f'/payments/{teacher.teacher_id}/settlement/', 'تسوية مدرس'),

        # Notifications (WhatsApp)
        ('/notifications/whatsapp/', 'لوحة الإشعارات'),
        ('/notifications/whatsapp/send/', 'إرسال رسالة'),
        ('/notifications/whatsapp/bulk/', 'إرسال جماعي'),
        ('/notifications/whatsapp/history/', 'سجل الرسائل'),
        ('/notifications/whatsapp/templates/', 'قوالب الرسائل'),

        # Reports
        ('/reports/', 'التقارير'),
        ('/reports/attendance/', 'تقرير الحضور'),
        ('/reports/payments/', 'تقرير المدفوعات'),

        # Bookings
        ('/teachers/bookings/', 'البحث عن المواعيد'),
        ('/teachers/bookings/calendar/', 'تقويم المواعيد'),
    ]

    for url, description in urls_to_test:
        try:
            response = client.get(url, follow=True)
            status = response.status_code

            # Check if page has data
            content = response.content.decode('utf-8', errors='ignore')
            has_data = len(content) > 500  # More than 500 chars usually means content

            results.add(url, status, has_data, description)

        except Exception as e:
            results.add(url, 500, False, f"Exception: {str(e)[:50]}")

    # Print results
    success = results.print_report()

    # Additional data checks
    print("\n📊 فحص البيانات في قاعدة البيانات:")
    print("-"*40)
    print(f"  👨‍🏫 المدرسين النشطين: {Teacher.objects.filter(is_active=True).count()}")
    print(f"  🏫 القاعات النشطة: {Room.objects.filter(is_active=True).count()}")
    print(f"  👥 المجموعات النشطة: {Group.objects.filter(is_active=True).count()}")
    print(f"  🎓 الطلاب النشطين: {Student.objects.filter(is_active=True).count()}")
    print(f"  📝 التسجيلات النشطة: {StudentGroupEnrollment.objects.filter(is_active=True).count()}")
    print(f"  💰 المدفوعات: {Payment.objects.count()}")

    return success


if __name__ == '__main__':
    print("\n" + "🚀"*20)
    print("  بدء الاختبارات الشاملة للنظام")
    print("🚀"*20)

    success = run_comprehensive_tests()

    if success:
        print("\n✅ جميع الاختبارات نجحت!")
    else:
        print("\n⚠️ بعض الاختبارات فشلت - راجع التقرير أعلاه")
