from django.core.management.base import BaseCommand
from apps.students.models import Student


class Command(BaseCommand):
    help = 'إعادة توليد باركود Code128 لجميع الطلاب'

    def handle(self, *args, **options):
        students = Student.all_objects.all()
        total = students.count()
        success = 0
        errors = 0

        self.stdout.write(f'بدء توليد الباركود لـ {total} طالب...')

        for student in students:
            try:
                student.save_barcode_image()
                success += 1
                if success % 50 == 0:
                    self.stdout.write(f'  تم معالجة {success}/{total}...')
            except Exception as e:
                errors += 1
                self.stderr.write(f'  خطأ في الطالب {student.student_code}: {e}')

        self.stdout.write(self.style.SUCCESS(
            f'تم الانتهاء: {success} نجح، {errors} فشل من أصل {total}'
        ))
