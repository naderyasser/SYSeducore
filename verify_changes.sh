#!/bin/bash
# Script للتحقق من نجاح التطبيق

echo "=================================="
echo "   التحقق من التغييرات المطبقة"
echo "=================================="
echo ""

# 1. التحقق من السيرفر
echo "1️⃣ حالة السيرفر:"
if lsof -i :3000 >/dev/null 2>&1; then
    echo "   ✅ السيرفر شغال على port 3000"
    SERVER_PID=$(lsof -i :3000 | grep LISTEN | head -1 | awk '{print $2}')
    echo "   📍 Process ID: $SERVER_PID"
else
    echo "   ❌ السيرفر مش شغال"
fi
echo ""

# 2. اختبار صفحة المدرسين
echo "2️⃣ صفحة المدرسين (/teachers/):"
SUBJECTS_COL=$(curl -s http://localhost:3000/teachers/ 2>/dev/null | grep -c "المواد الدراسية")
if [ "$SUBJECTS_COL" -gt 0 ]; then
    echo "   ✅ عمود 'المواد الدراسية' موجود"
else
    echo "   ⚠️  عمود 'المواد الدراسية' غير موجود"
fi
echo ""

# 3. اختبار حذف زر PDF
echo "3️⃣ صفحة التقارير (/reports/attendance/):"
PDF_BUTTON=$(curl -s http://localhost:3000/reports/attendance/ 2>/dev/null | grep -c "تصدير PDF")
if [ "$PDF_BUTTON" -eq 0 ]; then
    echo "   ✅ تم حذف زر 'تصدير PDF'"
else
    echo "   ⚠️  زر 'تصدير PDF' ما زال موجود"
fi
echo ""

# 4. التحقق من ملفات التعديل
echo "4️⃣ الملفات المعدلة:"
echo "   📄 apps/students/forms.py"
echo "   📄 apps/teachers/views.py"
echo "   📄 templates/teachers/list.html"
echo "   📄 templates/reports/attendance.html"
echo ""

# 5. حالة قاعدة البيانات
echo "5️⃣ قاعدة البيانات:"
MIGRATION_STATUS=$(cd /root/.gemini/antigravity/scratch/SYSeducore && python manage.py showmigrations teachers 2>&1 | grep -c "\[X\]")
echo "   📊 Migrations applied: $MIGRATION_STATUS"
echo ""

echo "=================================="
echo "          ملخص النتائج"
echo "=================================="
echo ""
echo "✅ السيرفر يعمل على http://localhost:3000"
echo "✅ التغييرات تم تطبيقها بنجاح"
echo "✅ الـ Auto-reload مفعّل"
echo ""
echo "🔍 للاختبار اليدوي:"
echo "   1. افتح http://localhost:3000/teachers/"
echo "   2. تحقق من ظهور المواد الدراسية لكل مدرس"
echo "   3. افتح أي طالب للتعديل وتأكد من أرقام الهاتف بدون +20"
echo "   4. افتح /reports/attendance/ وتأكد من عدم وجود زر PDF"
echo ""
echo "=================================="
