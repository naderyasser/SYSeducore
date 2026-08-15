"""
Notification Services
Handles SMS and WhatsApp notifications
"""

import logging

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('notifications')


class WhatsAppService:
    """
    WhatsApp Service using the Wapilot API v2
    يدعم الإرسال الفردي والجماعي

    Wapilot **queues** a message rather than delivering it inline: a 200 means
    the job was accepted and carries a ``message_id`` to track later, not that
    the parent's phone has the message. Callers therefore record ``sent``, never
    ``delivered`` — only a webhook can promote a row to ``delivered``.
    """

    def __init__(self):
        self.token = getattr(settings, 'WAPILOT_API_TOKEN', '')
        self.instance_id = getattr(settings, 'WAPILOT_INSTANCE_ID', '')
        self.base_url = getattr(
            settings, 'WAPILOT_API_BASE_URL', 'https://api.wapilot.net/api/v2'
        ).rstrip('/')

    @property
    def send_url(self):
        """``POST`` target for a text message on the configured instance."""
        return f'{self.base_url}/{self.instance_id}/send-message'

    def _headers(self, idempotency_key=None):
        """
        Auth + optional replay protection.

        Wapilot's documented public contract is a bare ``token`` header;
        ``Authorization: Bearer`` is only kept for backwards compatibility on
        their side, so the documented form is what we send.

        ``Idempotency-Key`` is the API-side twin of ``WhatsAppMessage.dedup_key``:
        the local unique constraint stops *this* system from sending twice, and
        the header stops a retry that crossed the network — a send whose reply
        was lost — from being delivered (and billed) twice.
        """
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'token': self.token,
        }
        if idempotency_key:
            headers['Idempotency-Key'] = str(idempotency_key)[:255]
        return headers

    def send_message(self, to, message, idempotency_key=None):
        """
        Queue a WhatsApp message via the Wapilot API.

        Args:
            to: Phone number (with country code, e.g., 201234567890 or +201234567890)
            message: Message text
            idempotency_key: Optional key making a client retry safe. Pass the
                caller's ``WhatsAppMessage.dedup_key`` so a retried Celery task
                cannot deliver the same message twice.

        Returns:
            Dictionary with result
        """
        if not self.token or not self.instance_id:
            # Fail loudly-but-safely: a missing instance id used to produce a
            # request to ``…/api/v2//send-message`` and a confusing 404.
            return {
                'success': False,
                'error': 'إعدادات الواتساب غير مكتملة (WAPILOT_API_TOKEN / WAPILOT_INSTANCE_ID)',
            }

        # Format phone number for Egyptian numbers
        phone = self._format_phone_number(to)

        data = {
            'chat_id': phone,
            'text': message,
        }

        try:
            response = requests.post(
                self.send_url,
                json=data,
                headers=self._headers(idempotency_key),
                timeout=10,
            )
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'خطأ في الاتصال: {str(e)}',
            }

        return self._parse_response(response)

    def _parse_response(self, response):
        """
        Translate a Wapilot reply into this project's ``{'success': ...}`` shape.

        Wapilot answers with JSON on every documented status, but an upstream
        proxy erroring out can still return HTML — hence the guarded decode.
        """
        try:
            result = response.json()
        except ValueError:
            return {
                'success': False,
                'error': f'رد غير متوقع من الخادم (HTTP {response.status_code})',
            }

        if response.status_code == 200 and result.get('success'):
            return {
                'success': True,
                'message_id': result.get('message_id'),
                # True when Wapilot recognised the Idempotency-Key and replayed
                # the original outcome instead of sending again.
                'idempotent_replay': bool(result.get('idempotent_replay')),
                'message': 'تم إرسال الرسالة بنجاح',
            }

        return {
            'success': False,
            'error': self._error_text(result, response.status_code),
        }

    @staticmethod
    def _error_text(result, status_code):
        """
        Build one readable Arabic-friendly error line out of a Wapilot failure.

        A 422 carries a per-field ``errors`` map that is far more useful than
        the generic ``"Validation failed."`` headline, so it is folded in.
        """
        message = result.get('message') or result.get('error') or 'فشل إرسال الرسالة'

        errors = result.get('errors')
        if isinstance(errors, dict) and errors:
            details = '; '.join(
                f"{field}: {' '.join(msgs) if isinstance(msgs, list) else msgs}"
                for field, msgs in errors.items()
            )
            message = f'{message} ({details})'

        code = result.get('code')
        if code:
            message = f'{message} [{code}]'

        return f'{message} (HTTP {status_code})'

    def get_instance_status(self):
        """
        Report whether the WhatsApp instance is actually linked to a phone.

        Sends nothing. Useful from the shell or a health page to tell the two
        indistinguishable-from-the-outside failures apart: a wrong token versus
        an instance whose QR code was never scanned (``SCAN_QR_CODE``).
        """
        if not self.token or not self.instance_id:
            return {'success': False, 'error': 'إعدادات الواتساب غير مكتملة'}

        url = f'{self.base_url}/instances/{self.instance_id}/status'
        try:
            response = requests.get(url, headers=self._headers(), timeout=10)
            result = response.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            return {'success': False, 'error': f'خطأ في الاتصال: {str(e)}'}

        if response.status_code == 200 and result.get('success'):
            return {
                'success': True,
                'status': result.get('status'),
                'connected': result.get('status') == 'WORKING',
                'phone': result.get('me_id'),
                'message': result.get('status_message', ''),
            }

        return {'success': False, 'error': self._error_text(result, response.status_code)}

    def send_bulk_message(self, phone_numbers, message):
        """
        الإرسال الجماعي - إرسال رسالة إلى مجموعة أرقام
        يمكن إرسال تقرير الحضور/الغياب أو التنبيهات إلى قائمة توزيع

        .. warning::
           **Never call this from a request thread** (PERF-03). Each send is a
           blocking HTTP call with a 10-second timeout, so 100 recipients can
           block for ~1000 s — far past gunicorn's 120 s limit, which kills the
           worker mid-send with the messages half-delivered.
           Use ``apps.notifications.tasks.send_bulk_whatsapp_task``: it runs on
           a Celery worker, records every message in ``WhatsAppMessage`` and is
           idempotent, so a retry never re-sends what already went out.

        Args:
            phone_numbers: قائمة أرقام الهواتف
            message: نص الرسالة

        Returns:
            Dictionary with results summary
        """
        results = {
            'total': len(phone_numbers),
            'success_count': 0,
            'fail_count': 0,
            'errors': []
        }

        for phone in phone_numbers:
            result = self.send_message(phone, message)
            if result.get('success'):
                results['success_count'] += 1
            else:
                results['fail_count'] += 1
                results['errors'].append({
                    'phone': phone,
                    'error': result.get('error', 'خطأ غير معروف')
                })

        return results

    def send_to_group_chat(self, group_id, message, idempotency_key=None):
        """
        الإرسال إلى مجموعة واتساب
        Send message to a WhatsApp group chat

        A group id (``…@g.us``) is a chat id like any other on Wapilot, so this
        goes through the same endpoint — it only skips the Egyptian phone
        formatting, which would mangle it.

        Args:
            group_id: WhatsApp group ID
            message: Message text
            idempotency_key: Optional key making a client retry safe.
        """
        if not self.token or not self.instance_id:
            return {
                'success': False,
                'error': 'إعدادات الواتساب غير مكتملة (WAPILOT_API_TOKEN / WAPILOT_INSTANCE_ID)',
            }

        data = {
            'chat_id': group_id,
            'text': message,
        }

        try:
            response = requests.post(
                self.send_url,
                json=data,
                headers=self._headers(idempotency_key),
                timeout=10,
            )
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'خطأ في الاتصال: {str(e)}',
            }

        result = self._parse_response(response)
        if result.get('success'):
            result['message'] = 'تم إرسال الرسالة للمجموعة بنجاح'
        return result

    def build_attendance_report(self, group, session_date=None):
        """
        بناء تقرير الحضور/الغياب لمجموعة كاملة (بدون إرسال)

        Returns ``(message, recipients)`` where *recipients* is a list of
        ``{'phone': ..., 'student': <Student>}`` — one entry per parent that
        has a phone number. Building is separated from sending so the Celery
        task can record a ``WhatsAppMessage`` row per recipient instead of
        firing a blind bulk loop (PERF-03).

        Raises ``LookupError`` with an Arabic message when the group has no
        session on that date.
        """
        from apps.students.models import StudentGroupEnrollment
        from apps.attendance.models import Attendance, Session

        if not session_date:
            # TZ-07: timezone.now().date() is the *UTC* date; between midnight
            # and 02:00/03:00 Cairo that is still yesterday.
            session_date = timezone.localdate()

        # Get session
        try:
            session = Session.objects.get(group=group, session_date=session_date)
        except Session.DoesNotExist:
            raise LookupError('لا توجد حصة لهذا التاريخ')

        # Get all enrollments — soft-deleted students must not appear on the
        # roster, and their parents must not be messaged.
        enrollments = StudentGroupEnrollment.objects.filter(
            group=group,
            is_active=True,
            student__deleted_at__isnull=True,
            student__is_active=True,
        ).select_related('student')

        recipients = []
        message_parts = [
            f'📋 *تقرير الحضور - {group.group_name}*',
            f'📅 التاريخ: {session_date.strftime("%Y/%m/%d")}',
            f'👨‍🏫 المدرس: {group.teacher.full_name}',
            '',
        ]

        present_count = 0
        absent_students = []

        for enrollment in enrollments:
            student = enrollment.student
            attendance = Attendance.objects.filter(
                student=student, session=session
            ).first()

            if attendance:
                message_parts.append(
                    f'✅ {student.full_name} - حاضر ({attendance.scan_time.strftime("%I:%M %p")})'
                )
                present_count += 1
            else:
                message_parts.append(f'❌ {student.full_name} - غائب')
                absent_students.append(student)

            # Collect parent phones
            if student.parent_phone:
                recipients.append({'phone': student.parent_phone, 'student': student})

        message_parts.append('')
        message_parts.append(f'📊 الإجمالي: {present_count} حاضر / {len(absent_students)} غائب')
        message_parts.append('')
        message_parts.append('_نظام الحضور الآلي_')

        return '\n'.join(message_parts), recipients

    def send_bulk_attendance_report(self, group, session_date=None):
        """
        إرسال تقرير حضور/غياب جماعي لمجموعة كاملة

        .. warning::
           Blocking: kept only for scripts and the shell. The web request path
           uses ``tasks.send_bulk_attendance_report_task`` (PERF-03).
        """
        try:
            message, recipients = self.build_attendance_report(group, session_date)
        except LookupError as exc:
            return {'success': False, 'error': str(exc)}

        return self.send_bulk_message([r['phone'] for r in recipients], message)

    #: Egypt country code, used only when the number is unmistakably local.
    DEFAULT_COUNTRY_CODE = '20'
    #: Length of an Egyptian mobile number written without the leading zero.
    EGYPT_LOCAL_LENGTH = 10

    def _format_phone_number(self, phone):
        """
        Format a phone number for the WhatsApp API (digits, country code first).

        DATA-28: the old implementation force-prefixed ``20`` onto *anything*
        that did not already start with ``20``, so ``+966501234567`` was
        mangled into ``20966501234567`` and delivered to a stranger — or to
        nobody. The rules now are:

        * an explicit international prefix (``+`` or ``00``) is respected and
          only stripped of its punctuation — never re-prefixed;
        * ``01xxxxxxxxx`` — the canonical stored format (see
          ``apps.students.utils.normalize_phone``) — becomes ``201xxxxxxxxx``;
        * a bare 10-digit local number gets the Egypt code;
        * anything already starting with ``20`` is left alone;
        * anything else is passed through as digits rather than guessed at.
        """
        raw = str(phone or '').strip()

        # Explicit international format: trust the caller, just normalise it.
        if raw.startswith('+'):
            return ''.join(filter(str.isdigit, raw))

        digits = ''.join(filter(str.isdigit, raw))
        if not digits:
            return digits

        # 00 <country code> ... is the other international prefix.
        if digits.startswith('00'):
            return digits[2:]

        # Local Egyptian format 01xxxxxxxxx -> 201xxxxxxxxx
        if digits.startswith('0'):
            return self.DEFAULT_COUNTRY_CODE + digits[1:]

        if digits.startswith(self.DEFAULT_COUNTRY_CODE):
            return digits

        # A bare local number with the trunk zero dropped.
        if len(digits) == self.EGYPT_LOCAL_LENGTH:
            return self.DEFAULT_COUNTRY_CODE + digits

        # Unknown shape (already a foreign country code, a short code, ...) —
        # sending it unchanged is far safer than inventing an Egyptian number.
        return digits

    def build_attendance_message(self, student_name, status, time):
        """
        نص رسالة الحضور/الغياب

        Exposed separately from :meth:`send_attendance_notification` so callers
        that must *record* what they sent (the Celery tasks) can store the exact
        text in ``WhatsAppMessage.message_text``.
        """
        if status == 'present':
            return self._get_present_message(student_name, time)
        if status == 'late':
            return self._get_late_message(student_name, time)
        return self._get_absent_message(student_name)

    def build_monthly_reminder_message(self, student_name, group_name, amount):
        """نص رسالة تذكير المصروفات الشهرية"""
        return self._get_payment_reminder_message(student_name, group_name, amount)

    def send_attendance_notification(self, student_name, parent_phone, status, time):
        """
        Send attendance notification to parent

        Args:
            student_name: Student name
            parent_phone: Parent's phone number
            status: Attendance status (present, late, absent)
            time: Attendance time
        """
        message = self.build_attendance_message(student_name, status, time)
        return self.send_message(parent_phone, message)


    def send_monthly_reminder(self, student_name, parent_phone, group_name, amount):
        """
        Send monthly payment reminder
        
        Args:
            student_name: Student name
            parent_phone: Parent's phone number
            group_name: Group name
            amount: Amount due
        """
        message = self._get_payment_reminder_message(student_name, group_name, amount)
        return self.send_message(parent_phone, message)
    
    def send_warning_before_block(self, student_name, parent_phone, amount):
        """
        Send warning before blocking student

        Args:
            student_name: Student name
            parent_phone: Parent's phone number
            amount: Amount due
        """
        message = self._get_warning_message(student_name, amount)
        return self.send_message(parent_phone, message)

    def send_block_notification(self, student_name, parent_phone, reason='late'):
        """
        Send notification when student is blocked

        Args:
            student_name: Student name
            parent_phone: Parent's phone number
            reason: Block reason ('late' or 'payment')
        """
        if reason == 'late':
            message = self._get_late_block_message(student_name)
        else:
            message = self._get_payment_block_message(student_name)
        return self.send_message(parent_phone, message)

    def _get_late_block_message(self, student_name):
        """Get late block message"""
        time_str = timezone.now().strftime('%I:%M %p')
        return f'''⛔ *تم منع الدخول - تأخير*

تم منع ابنكم *{student_name}* من دخول الحصة
السبب: التأخر أكثر من 10 دقائق عن الموعد المحدد
الوقت: {time_str}

يُرجى الالتزام بمواعيد الحصص

_نظام الحضور الآلي_'''

    def _get_payment_block_message(self, student_name):
        """Get payment block message"""
        return f'''⛔ *تم منع الدخول - مصروفات*

تم منع ابنكم *{student_name}* من دخول الحصة
السبب: عدم سداد المصروفات المطلوبة

يُرجى مراجعة الإدارة لسداد المصروفات

_نظام الحضور الآلي_'''
    
    def _get_present_message(self, student_name, time):
        """Get present attendance message"""
        time_str = time.strftime('%I:%M %p')
        return f'''✅ *تم تسجيل الحضور*

وصل ابنكم *{student_name}* إلى السنتر بنجاح
الوقت: {time_str}
الحالة: حاضر في الموعد ⏰

_نظام الحضور الآلي_'''
    
    def _get_late_message(self, student_name, time):
        """Get late attendance message"""
        time_str = time.strftime('%I:%M %p')
        return f'''⚠️ *تم تسجيل الحضور - متأخر*

وصل ابنكم *{student_name}* إلى السنتر
الوقت: {time_str}
الحالة: متأخر 🕐

يُرجى الالتزام بالمواعيد المحددة

_نظام الحضور الآلي_'''
    
    def _get_absent_message(self, student_name):
        """Get absence message"""
        date_str = timezone.now().strftime('%Y/%m/%d')
        return f'''❌ *تنبيه غياب*

تغيب ابنكم *{student_name}* عن الحصة اليوم
التاريخ: {date_str}

للاستفسار يُرجى التواصل مع الإدارة

_نظام الحضور الآلي_'''
    
    def _get_payment_reminder_message(self, student_name, group_name, amount):
        """Get payment reminder message"""
        return f'''💰 *تذكير بالمصروفات الشهرية*

عزيزي ولي أمر الطالب *{student_name}*

المجموعة: {group_name}
المصروفات المطلوبة: *{amount} جنيه*

يُرجى سداد المصروفات لضمان استمرار حضور الطالب

للدفع أو الاستفسار يُرجى التواصل مع الإدارة

_نظام الحضور الآلي_'''
    
    def _get_warning_message(self, student_name, amount):
        """Get warning before blocking message"""
        return f'''⚠️ *تنبيه هام - يُرجى الدفع*

عزيزي ولي أمر الطالب *{student_name}*

حضر الطالب 2 حصص هذا الشهر
المبلغ المطلوب: *{amount} جنيه*

⚠️ في حالة عدم السداد، سيتم منع الطالب من حضور الحصة القادمة

يُرجى سرعة السداد

_نظام الحضور الآلي_'''


class NotificationService:
    """
    Main notification service with fallback strategy
    """
    
    _disabled_response = {'success': True, 'skipped': True, 'message': 'Notifications disabled'}

    def __init__(self):
        self.whatsapp_service = WhatsAppService()
        self.notification_method = getattr(settings, 'NOTIFICATION_METHOD', 'whatsapp')

    @property
    def is_disabled(self):
        return self.notification_method not in ('whatsapp',)

    def send_attendance_notification(self, student_name, parent_phone, status, time):
        """
        Send attendance notification with fallback
        """
        if self.is_disabled:
            return self._disabled_response
        if self.notification_method == 'whatsapp':
            return self.whatsapp_service.send_attendance_notification(
                student_name, parent_phone, status, time
            )
        
        # Add other notification methods here if needed
        
        return {'success': False, 'error': 'طريقة الإشعار غير مدعومة'}
    
    def send_text(self, phone, message, idempotency_key=None):
        """
        Send an already-composed message, honouring the disabled switch.

        Callers that must record exactly what they sent build the text
        themselves (via the ``build_*`` helpers) and hand it to this method.

        ``idempotency_key`` should be the caller's ``WhatsAppMessage.dedup_key``.
        The local unique constraint already stops a *reserved* message from
        being sent twice; the key closes the remaining window, where the send
        left this process, was accepted by Wapilot, and the reply was lost — a
        retry then reuses the key and Wapilot replays the original result
        instead of delivering a second copy.
        """
        if self.is_disabled:
            return self._disabled_response
        if self.notification_method == 'whatsapp':
            return self.whatsapp_service.send_message(
                phone, message, idempotency_key=idempotency_key
            )

        return {'success': False, 'error': 'طريقة الإشعار غير مدعومة'}

    def send_monthly_reminder(self, student_name, parent_phone, group_name, amount):
        """
        Send monthly payment reminder with fallback
        """
        if self.is_disabled:
            return self._disabled_response
        if self.notification_method == 'whatsapp':
            return self.whatsapp_service.send_monthly_reminder(
                student_name, parent_phone, group_name, amount
            )

        return {'success': False, 'error': 'طريقة الإشعار غير مدعومة'}

    def send_monthly_reminders(self, month=None):
        """
        إرسال تذكيرات المصروفات الشهرية لجميع الطلاب غير المسددين (BUG-02)

        The monthly cron used to call this method — which did not exist — so
        ``AttributeError`` was raised on the 1st of every month and **no
        reminder was ever sent**.

        Behaviour:

        * unpaid / partially-paid ``Payment`` rows of *month* (default: the
          current local month) are collected, skipping exempt rows, zero-fee
          rows, soft-deleted / inactive students and students with no parent
          phone;
        * the rows of one student are merged into **one** message listing the
          groups and the total outstanding amount, so a student enrolled in
          three groups does not get three WhatsApps;
        * every send is recorded in ``WhatsAppMessage`` under the idempotency
          key ``monthly-reminder:<YYYY-MM>:<student_id>``, so re-running the
          task — a Celery retry, a duplicated beat tick, a manual re-run — can
          never send (or pay for) the same reminder twice.

        Returns a summary dict.
        """
        from django.db import IntegrityError, transaction

        from apps.payments.models import Payment

        from .models import WhatsAppMessage

        summary = {'total': 0, 'sent': 0, 'failed': 0, 'skipped': 0}

        if month is None:
            month = timezone.localdate().replace(day=1)
        else:
            month = month.replace(day=1)

        if self.is_disabled:
            logger.info('Monthly reminders skipped: notifications are disabled')
            summary['disabled'] = True
            return summary

        payments = (
            Payment.objects.filter(
                month=month,
                status__in=['unpaid', 'partial'],
                is_exempt=False,
                amount_due__gt=0,
                student__is_active=True,
                student__deleted_at__isnull=True,
            )
            .select_related('student', 'group')
            .order_by('student_id', 'payment_id')
        )

        # Merge every outstanding row of the same student into one reminder.
        per_student = {}
        for payment in payments:
            student = payment.student
            outstanding = (payment.amount_due or 0) - (payment.amount_paid or 0)
            if outstanding <= 0:
                continue
            entry = per_student.setdefault(
                student.pk, {'student': student, 'groups': [], 'amount': 0}
            )
            entry['amount'] += outstanding
            group_name = payment.group.group_name if payment.group else ''
            if group_name and group_name not in entry['groups']:
                entry['groups'].append(group_name)

        month_key = month.strftime('%Y-%m')

        for entry in per_student.values():
            student = entry['student']
            summary['total'] += 1

            phone = (student.parent_phone or '').strip()
            if not phone:
                summary['skipped'] += 1
                continue

            message = self.whatsapp_service.build_monthly_reminder_message(
                student.full_name,
                ' ، '.join(entry['groups']) or '-',
                entry['amount'],
            )

            dedup_key = f'monthly-reminder:{month_key}:{student.pk}'
            try:
                with transaction.atomic():
                    record = WhatsAppMessage.objects.create(
                        dedup_key=dedup_key,
                        phone_number=phone,
                        message_text=message,
                        message_type='payment',
                        student=student,
                        status='pending',
                    )
            except IntegrityError:
                # Already reminded for this month — never send twice.
                summary['skipped'] += 1
                continue

            result = self.send_text(phone, message, idempotency_key=dedup_key)
            succeeded = bool(result.get('success'))
            record.status = 'sent' if succeeded else 'failed'
            record.sent_at = timezone.now() if succeeded else None
            record.error_message = result.get('error', '') or ''
            record.save(update_fields=['status', 'sent_at', 'error_message', 'updated_at'])

            if succeeded:
                summary['sent'] += 1
            else:
                summary['failed'] += 1

        logger.info(
            'Monthly reminders for %s: %s sent, %s failed, %s skipped',
            month_key, summary['sent'], summary['failed'], summary['skipped'],
        )
        return summary


    def send_warning_before_block(self, student_name, parent_phone, amount):
        """
        Send warning before blocking with fallback
        """
        if self.is_disabled:
            return self._disabled_response
        if self.notification_method == 'whatsapp':
            return self.whatsapp_service.send_warning_before_block(
                student_name, parent_phone, amount
            )

        return {'success': False, 'error': 'طريقة الإشعار غير مدعومة'}

    def send_block_notification(self, student_name, parent_phone, reason='late'):
        """
        Send block notification with fallback
        """
        if self.is_disabled:
            return self._disabled_response
        if self.notification_method == 'whatsapp':
            return self.whatsapp_service.send_block_notification(
                student_name, parent_phone, reason
            )

        return {'success': False, 'error': 'طريقة الإشعار غير مدعومة'}
