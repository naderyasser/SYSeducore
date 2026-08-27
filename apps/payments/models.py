from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone

TWO_PLACES = Decimal('0.01')
ZERO = Decimal('0.00')


class PaymentAmountError(ValueError):
    """
    خطأ في مبلغ الدفع.

    Raised by :meth:`Payment.record_transaction` when a money movement is
    rejected (non-numeric, negative, or larger than the outstanding
    balance). The message is Arabic and safe to show to the user.
    """


def to_money(value):
    """
    Coerce *value* to a 2-decimal :class:`~decimal.Decimal`.

    Raises :class:`PaymentAmountError` (Arabic message) instead of letting
    ``decimal.InvalidOperation`` escape as a 500. ``float`` input is routed
    through ``str()`` so binary rounding never reaches the database.
    """
    if isinstance(value, Decimal):
        amount = value
    else:
        try:
            amount = Decimal(str(value).strip())
        except (InvalidOperation, ValueError, TypeError, AttributeError):
            raise PaymentAmountError('قيمة المبلغ غير صالحة')
    if not amount.is_finite():
        raise PaymentAmountError('قيمة المبلغ غير صالحة')
    try:
        return amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise PaymentAmountError('قيمة المبلغ غير صالحة')


class PaymentPackage(models.Model):
    """
    شراء عدة دورات مقدَّمًا (باقة)، عادة بسعر مخفَّض عن مجموع الدورات منفردة.

    يُمثَّل الغطاء بصف :class:`Payment` واحد **لكل دورة** (وليس بحقل "عدد
    الدورات" على صف دفعة واحدة) — تصفية المدرس تحاسب بالدورة المُغلقة فعليًا،
    فتوزيع المبلغ على صفوف منفصلة يمنع احتساب 100% من قيمة الباقة في شهر
    تحصيل واحد ثم عجزًا وهميًا في الشهر التالي.
    """
    package_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.PROTECT,
        related_name='payment_packages',
        verbose_name="الطالب",
    )
    group = models.ForeignKey(
        'teachers.Group',
        on_delete=models.PROTECT,
        related_name='payment_packages',
        verbose_name="المجموعة",
    )
    cycles = models.PositiveSmallIntegerField(verbose_name="عدد الدورات")
    total_amount = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="المبلغ الإجمالي المدفوع"
    )
    list_amount = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="المبلغ الإجمالي بدون خصم"
    )
    paid_on = models.DateField(verbose_name="تاريخ الدفع")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='payment_packages_created',
        verbose_name="أنشئت بواسطة",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payment_packages'
        verbose_name = 'باقة دفع'
        verbose_name_plural = 'باقات الدفع'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.full_name} - {self.group.group_name} - {self.cycles} دورات"

    @property
    def discount(self):
        return to_money(self.list_amount) - to_money(self.total_amount)


class Payment(models.Model):
    """
    Payment model for managing student payments.
    الطالب الآن يمكن أن يكون لديه مدفوعات متعددة لمجموعات مختلفة في نفس الشهر

    ``amount_paid`` is **reconciled from** :class:`PaymentTransaction`: every
    money movement must go through :meth:`record_transaction` /
    :meth:`settle_full` / :meth:`reverse_all`, which write a ledger row and
    then recompute ``amount_paid``, ``status`` and ``payment_date`` from the
    ledger. Assigning ``amount_paid`` directly still works (legacy code and
    fixtures do it) but leaves no audit trail; the next ledger operation
    reconciles the difference into an explicit "رصيد سابق" row rather than
    silently losing it.
    """
    STATUS_CHOICES = [
        ('paid', 'مدفوع'),
        ('partial', 'مدفوع جزئياً'),
        ('unpaid', 'غير مدفوع'),
    ]

    payment_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.PROTECT,
        related_name='payments'
    )
    group = models.ForeignKey(
        'teachers.Group',
        on_delete=models.PROTECT,
        related_name='payments',
        verbose_name="المجموعة"
    )

    cycle = models.ForeignKey(
        'teachers.GroupCycle',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='payments',
        verbose_name="دورة الفوترة",
        help_text="مفتاح الفوترة الفعلي — ``month`` يبقى مشتقًا منه للتوافق مع التقارير القديمة",
    )
    package = models.ForeignKey(
        'PaymentPackage',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='payments',
        verbose_name="الباقة",
    )

    month = models.DateField(verbose_name="الشهر", db_index=True)
    amount_due = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name="المبلغ المطلوب"
    )
    amount_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="المبلغ المدفوع"
    )

    payment_date = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الدفع")
    paid_on = models.DateField(
        null=True, blank=True,
        verbose_name="تاريخ الدفع",
        help_text=(
            "التاريخ الفعلي الذي دفع فيه ولي الأمر (يُدخله الموظف يدويًا) — "
            "بخلاف payment_date المُشتق تلقائيًا من سجل الحركات المحاسبي"
        ),
    )
    entitlement_start_session = models.ForeignKey(
        'attendance.Session',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='+',
        verbose_name="أول حصة مستحقة",
    )
    entitlement_start_seq = models.PositiveSmallIntegerField(
        null=True, blank=True,
        verbose_name="ترتيب أول حصة مستحقة في الدورة",
    )
    sessions_attended = models.PositiveIntegerField(default=0, verbose_name="عدد الحصص المستهلكة")
    sessions_total = models.PositiveIntegerField(default=4, verbose_name="عدد الحصص المستحقة")
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='unpaid',
        verbose_name="الحالة"
    )
    is_exempt = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="إعفاء كامل",
        help_text=(
            "صف مُعفى (مصروفات = صفر). يُحسب كـ«مدفوع» لأغراض الحضور فقط "
            "ولا يدخل في نسبة التحصيل."
        ),
    )

    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    billing_cycle_completed = models.BooleanField(
        default=False,
        verbose_name="اكتملت دورة الفوترة",
        help_text="هل اكتملت دورة الفوترة لهذا الشهر وبدأت دورة جديدة",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='payments_created',
        verbose_name="أنشئت بواسطة",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payments'
        # مفتاح الفوترة الحقيقي أصبح (student, cycle) لا (student, group, month):
        # مجموعة بحصص 8 يمكن أن تُغلق دورتان فيها داخل نفس الشهر التقويمي، وهو
        # ما كان يفشل تحت القيد القديم. صفوف قديمة بلا دورة (cycle=None) لا
        # تتعارض مع بعضها — NULL لا يساوي NULL في قيود التفرد.
        constraints = [
            models.UniqueConstraint(fields=['student', 'cycle'], name='uniq_payment_student_cycle'),
        ]
        ordering = ['-month']

    def __str__(self):
        return f"{self.student.full_name} - {self.group.group_name} - {self.month.strftime('%Y-%m')}"

    def save(self, *args, **kwargs):
        """
        Enforce ``is_exempt`` for zero-fee rows regardless of which code
        created them. ``_ensure_monthly_payments`` sets the flag explicitly,
        but every other creation path (subscription activation, attendance
        services, the student form) just writes ``amount_due=0`` — leaving
        ``is_exempt`` False makes a zero-fee row look like a real (100%)
        collection in the stats.
        """
        if self.amount_due is not None and self.amount_due <= 0 and not self.is_exempt:
            self.is_exempt = True
            update_fields = kwargs.get('update_fields')
            if update_fields is not None and 'is_exempt' not in update_fields:
                kwargs['update_fields'] = list(update_fields) + ['is_exempt']
        super().save(*args, **kwargs)

    @property
    def remaining(self):
        return self.amount_due - self.amount_paid

    # ------------------------------------------------------------------
    #  Ledger (audit trail)
    # ------------------------------------------------------------------

    def ledger_total(self):
        """Sum of every recorded movement (سجل الحركات)."""
        total = self.transactions.aggregate(total=models.Sum('amount'))['total']
        return to_money(total) if total is not None else ZERO

    def sync_ledger(self, user=None):
        """
        Make the ledger explain ``amount_paid``.

        Rows created before the ledger existed — or written by legacy code
        that assigns ``amount_paid`` directly — would otherwise be erased by
        the first reconciliation. Any unexplained positive balance is turned
        into an explicit opening-balance row instead. Returns the ledger
        total afterwards.
        """
        total = self.ledger_total()
        current = to_money(self.amount_paid or 0)
        gap = current - total
        if gap > 0:
            PaymentTransaction.objects.create(
                payment=self,
                amount=gap,
                kind=PaymentTransaction.KIND_OPENING,
                created_by=user,
                note='رصيد سابق مُسجَّل خارج سجل الحركات — تسوية تلقائية',
            )
            total = current
        return total

    def _derive_status(self, total):
        if self.is_exempt or self.amount_due <= 0:
            # Zero-fee / exempt rows are settled by definition; ``is_exempt``
            # is what separates them from real collections.
            return 'paid'
        if total >= self.amount_due:
            return 'paid'
        if total > 0:
            return 'partial'
        return 'unpaid'

    def _apply_ledger_total(self, total, save=True):
        """Write a known ledger total onto the payment row."""
        self.amount_paid = total
        self.status = self._derive_status(total)

        if total > 0:
            last = self.transactions.order_by('-created_at', '-transaction_id').first()
            self.payment_date = last.created_at if last else (self.payment_date or timezone.now())
        else:
            self.payment_date = None

        if save:
            self.save(update_fields=['amount_paid', 'status', 'payment_date', 'updated_at'])
        return total

    def reconcile(self, user=None, save=True):
        """
        Recompute ``amount_paid`` / ``status`` / ``payment_date`` from the
        ledger. Returns the ledger total.
        """
        return self._apply_ledger_total(self.sync_ledger(user=user), save=save)

    @transaction.atomic
    def record_transaction(self, amount, user=None, note='', kind=None, allow_reversal=False,
                            effective_on=None):
        """
        Record one money movement and reconcile the payment.

        * ``amount`` may be any numeric/str value; it is coerced to Decimal.
        * A negative amount is rejected unless ``allow_reversal=True`` (only
          the admin reversal actions pass it), so a payment can never be
          silently reversed through the desk API.
        * The resulting total may never exceed ``amount_due`` nor drop below
          zero.
        * ``amount == 0`` is a no-op that still reconciles (the desk UI posts
          0 when the cashier clears the field).
        * ``effective_on`` is the business date the desk was told the money
          changed hands (defaults to today) — recorded on the ledger row and
          mirrored onto ``Payment.paid_on`` for a real (positive) movement.
          ``PaymentTransaction.created_at`` itself is never back-dated: it
          stays the untouchable audit timestamp of when the row was written.

        Returns the created :class:`PaymentTransaction`, or ``None`` for a
        zero-amount no-op. Raises :class:`PaymentAmountError` — Arabic
        message — on any rejection.
        """
        amount = to_money(amount)
        effective_on = effective_on or timezone.localdate()

        if amount < 0 and not allow_reversal:
            raise PaymentAmountError('لا يمكن تسجيل مبلغ سالب')

        # Lock the row so two cashiers cannot both pass the over-payment
        # check on the same payment (no-op on SQLite, real on PostgreSQL).
        locked = Payment.objects.select_for_update().get(pk=self.pk)

        ledger = locked.sync_ledger(user=user)
        new_total = ledger + amount

        if new_total < 0:
            raise PaymentAmountError('لا يمكن أن يصبح إجمالي المدفوع بالسالب')

        if amount > 0 and new_total > locked.amount_due:
            outstanding = locked.amount_due - ledger
            raise PaymentAmountError(
                f'المبلغ أكبر من المتبقي على الطالب (المتبقي: {outstanding} ج.م)'
            )

        txn = None
        if amount != 0:
            txn = PaymentTransaction.objects.create(
                payment=locked,
                amount=amount,
                kind=kind or (
                    PaymentTransaction.KIND_REVERSAL if amount < 0
                    else PaymentTransaction.KIND_PAYMENT
                ),
                created_by=user,
                note=note,
                effective_on=effective_on,
            )

        # Apply the already-known total: re-reading the ledger through
        # ``sync_ledger`` here would see the (now stale) ``amount_paid`` of
        # the locked row and "restore" a reversal as an opening balance.
        locked._apply_ledger_total(new_total)
        if amount > 0:
            locked.paid_on = effective_on
            locked.save(update_fields=['paid_on'])

        # Mirror the reconciled state onto the caller's instance.
        self.amount_paid = locked.amount_paid
        self.status = locked.status
        self.payment_date = locked.payment_date
        self.paid_on = locked.paid_on
        return txn

    @transaction.atomic
    def settle_full(self, user=None, note='', effective_on=None):
        """
        تسديد كامل — record the outstanding balance as one movement.

        Idempotent: an already-settled payment records nothing and simply
        reconciles. Returns the created transaction or ``None``.
        """
        ledger = self.sync_ledger(user=user)
        outstanding = to_money(self.amount_due) - ledger
        if outstanding <= 0:
            self.reconcile(user=user)
            return None
        return self.record_transaction(
            outstanding,
            user=user,
            note=note or 'تسديد كامل',
            effective_on=effective_on,
        )

    def reverse_all(self, user=None, note=''):
        """
        تصفير — reverse the whole recorded balance with an explicit negative
        movement, so the reversal itself stays in the audit trail.
        """
        total = self.sync_ledger(user=user)
        if total == 0:
            self.reconcile(user=user)
            return None
        return self.record_transaction(
            -total,
            user=user,
            note=note or 'تصفير المدفوعات',
            kind=PaymentTransaction.KIND_REVERSAL,
            allow_reversal=True,
        )


class PaymentTransaction(models.Model):
    """
    سجل حركات الدفع — an immutable receipt line for every money movement.

    ``Payment.amount_paid`` is the reconciled sum of these rows: this table
    is what answers "who took this money, when, and how much".
    """
    KIND_PAYMENT = 'payment'
    KIND_REVERSAL = 'reversal'
    KIND_OPENING = 'opening'
    KIND_ADJUSTMENT = 'adjustment'

    KIND_CHOICES = [
        (KIND_PAYMENT, 'دفعة'),
        (KIND_REVERSAL, 'عكس/استرداد'),
        (KIND_OPENING, 'رصيد سابق'),
        (KIND_ADJUSTMENT, 'تسوية'),
    ]

    transaction_id = models.AutoField(primary_key=True)
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name='transactions',
        verbose_name="الدفعة",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="المبلغ",
        help_text="موجب للتحصيل، سالب لعكس عملية سابقة",
    )
    kind = models.CharField(
        max_length=12,
        choices=KIND_CHOICES,
        default=KIND_PAYMENT,
        verbose_name="نوع الحركة",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='payment_transactions',
        verbose_name="بواسطة",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="التاريخ")
    effective_on = models.DateField(
        null=True, blank=True,
        verbose_name="تاريخ الدفع الفعلي",
        help_text=(
            "التاريخ الذي أعطاه ولي الأمر (قد يسبق created_at)، بخلاف "
            "created_at الذي يبقى ثابتًا ولا يُعدَّل أبدًا كدليل تدقيق"
        ),
    )
    note = models.TextField(blank=True, verbose_name="ملاحظة")

    class Meta:
        db_table = 'payment_transactions'
        ordering = ['-created_at', '-transaction_id']
        verbose_name = 'حركة دفع'
        verbose_name_plural = 'حركات الدفع'
        indexes = [
            models.Index(fields=['payment', 'created_at'], name='paytxn_payment_created_idx'),
        ]

    def __str__(self):
        who = self.created_by.get_username() if self.created_by else 'النظام'
        return f"{self.payment_id} — {self.amount} ج.م — {who}"


class SettlementLockedError(Exception):
    """الكشف معتمد — لا يمكن تعديله قبل إعادة فتحه."""


class TeacherSettlement(models.Model):
    """
    كشف تصفية مدرس عن فترة معينة — رأس الكشف. يُحتسَب بالحصص المستهلكة
    فعليًا (لا بافتراض أن كل طالب أكمل الدورة)، ويمكن تعديله يدويًا أثناء
    المحاسبة (استبعاد طالب، تخفيض مبلغ، تعديل نسبة) قبل اعتماده.

    ``computed_*`` مبنية من مجموع ``TeacherSettlementLine`` — الحساب الفعلي
    في ``apps.payments.services.SettlementService``.
    """
    STATUS_DRAFT = 'draft'
    STATUS_APPROVED = 'approved'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'مسودة'),
        (STATUS_APPROVED, 'معتمد'),
    ]

    settlement_id = models.AutoField(primary_key=True)
    teacher = models.ForeignKey(
        'teachers.Teacher', on_delete=models.PROTECT, related_name='settlements',
        verbose_name="المدرس",
    )
    period_start = models.DateField(verbose_name="بداية الفترة")
    period_end = models.DateField(verbose_name="نهاية الفترة")
    period_label = models.CharField(max_length=64, blank=True, verbose_name="تسمية الفترة")
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True,
        verbose_name="الحالة",
    )

    computed_gross = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="الإجمالي المحسوب")
    adjusted_gross = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="الإجمالي بعد التعديل")
    center_share = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="نصيب المركز")
    teacher_share = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="نصيب المدرس")
    default_center_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('30.00'), verbose_name="نسبة المركز الافتراضية",
    )

    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='settlements_created', verbose_name="أنشئت بواسطة",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='settlements_approved', verbose_name="اعتُمد بواسطة",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='settlements_reopened', verbose_name="أُعيد فتحه بواسطة",
    )
    reopened_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'teacher_settlements'
        unique_together = [('teacher', 'period_start', 'period_end')]
        ordering = ['-period_start', 'teacher_id']
        indexes = [
            models.Index(fields=['teacher', 'status'], name='settle_teacher_status_idx'),
        ]
        verbose_name = 'كشف تصفية مدرس'
        verbose_name_plural = 'كشوفات تصفية المدرسين'

    def __str__(self):
        return f"{self.teacher.full_name} — {self.period_start} إلى {self.period_end} ({self.get_status_display()})"

    @property
    def is_approved(self):
        return self.status == self.STATUS_APPROVED

    def recalculate_totals(self):
        """أعِد حساب مجاميع الرأس من مجموع سطوره — استعلام واحد."""
        agg = self.lines.aggregate(
            computed=models.Sum('computed_amount'),
            adjusted=models.Sum('effective_amount'),
            center=models.Sum('line_center_share'),
            teacher=models.Sum('line_teacher_share'),
        )
        self.computed_gross = agg['computed'] or ZERO
        self.adjusted_gross = agg['adjusted'] or ZERO
        self.center_share = agg['center'] or ZERO
        self.teacher_share = agg['teacher'] or ZERO
        self.save(update_fields=['computed_gross', 'adjusted_gross', 'center_share', 'teacher_share', 'updated_at'])


class TeacherSettlementLine(models.Model):
    """
    سطر تصفية لطالب واحد ضمن مجموعة واحدة داخل كشف مدرس.

    ثلاث مجموعات من الحقول متعمَّد فصلها:
      * **لقطة (snapshot)** — ما حسبه النظام؛ تُعاد كتابتها عند "إعادة الحساب"
        فقط، ولا تُمس التعديلات اليدوية أبدًا.
      * **تعديل يدوي (override)** — ``None`` تعني "لا يوجد تعديل"، ليست صفرًا.
      * **مُشتقّ (derived)** — محفوظ لا يُحسب وقت العرض، فتبقى القراءة رخيصة
        والكشف مفهومًا بعد سنوات حتى لو تغيّرت الأسعار والنسب.
    """
    line_id = models.AutoField(primary_key=True)
    settlement = models.ForeignKey(
        TeacherSettlement, on_delete=models.CASCADE, related_name='lines',
        verbose_name="الكشف",
    )
    group = models.ForeignKey(
        'teachers.Group', on_delete=models.PROTECT, related_name='settlement_lines',
        verbose_name="المجموعة",
    )
    student = models.ForeignKey(
        'students.Student', on_delete=models.PROTECT, related_name='settlement_lines',
        verbose_name="الطالب",
    )
    cycle = models.ForeignKey(
        'teachers.GroupCycle', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='settlement_lines', verbose_name="الدورة",
    )
    payment = models.ForeignKey(
        Payment, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='settlement_lines', verbose_name="الدفعة (للتتبع فقط)",
    )

    # ── لقطة: ما حسبه النظام وقت البناء/إعادة الحساب ──
    sessions_consumed = models.PositiveIntegerField(default=0, verbose_name="الحصص المستهلكة")
    sessions_entitled = models.PositiveIntegerField(default=0, verbose_name="الحصص المستحقة")
    session_dates = models.JSONField(default=list, blank=True, verbose_name="تواريخ الحصص")
    fee_full = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="السعر الكامل للدورة")
    computed_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="المبلغ المحسوب آليًا")
    collected_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="المبلغ المُحصَّل فعليًا")
    financial_status = models.CharField(max_length=15, blank=True, verbose_name="الحالة المالية")
    group_center_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('30.00'), verbose_name="نسبة المركز للمجموعة",
    )

    # ── تعديل يدوي — None يعني "لا تعديل" ──
    is_excluded = models.BooleanField(default=False, verbose_name="مستبعد")
    is_free = models.BooleanField(default=False, verbose_name="حالة مجانية/خاصة")
    amount_override = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="مبلغ مُعدَّل",
    )
    percentage_override = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="نسبة مُعدَّلة",
    )
    override_reason = models.CharField(max_length=255, blank=True, verbose_name="سبب التعديل")

    # ── مُشتقّ ومحفوظ ──
    effective_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="المبلغ الفعلي بعد التعديل")
    line_center_share = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="نصيب المركز")
    line_teacher_share = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="نصيب المدرس")

    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='settlement_lines_edited', verbose_name="آخر مُعدِّل",
    )
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'teacher_settlement_lines'
        unique_together = [('settlement', 'group', 'student')]
        ordering = ['group__group_name', 'student__full_name']
        indexes = [
            models.Index(fields=['settlement', 'group'], name='settleline_stl_grp_idx'),
        ]
        verbose_name = 'سطر تصفية'
        verbose_name_plural = 'سطور التصفية'

    def __str__(self):
        return f"{self.student.full_name} — {self.group.group_name}"

    def save(self, *args, **kwargs):
        """
        يمنع أي تعديل على سطر ينتمي لكشف مُعتمَد، حتى لو تم تجاوز واجهة
        العرض (شِل، أمر إداري). ``force_locked=True`` يُتيح إعادة الفتح نفسها
        (تكتب على الرأس لا على السطر، فلا تحتاج هذا أصلًا) وأي عملية نظامية
        موثوقة صراحةً.
        """
        force = kwargs.pop('force_locked', False)
        if self.settlement_id and not force:
            if self.settlement.status == TeacherSettlement.STATUS_APPROVED:
                raise SettlementLockedError('الكشف معتمد — لا يمكن تعديله')
        super().save(*args, **kwargs)

    def apply(self):
        """
        طبّق قواعد الحساب (استبعاد/مجاني/تعديل مبلغ/تعديل نسبة) وخزّن
        الأعمدة المُشتقّة. لا تحفظ — الاستدعاء يقرر متى.
        """
        if self.is_excluded:
            base = center = teacher = ZERO
        else:
            if self.is_free:
                base = ZERO
            elif self.amount_override is not None:
                base = to_money(self.amount_override)
            else:
                base = to_money(self.computed_amount)

            pct = (
                self.percentage_override if self.percentage_override is not None
                else self.group_center_percentage
            )
            center = (base * pct / Decimal('100')).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            teacher = base - center

        self.effective_amount = base
        self.line_center_share = center
        self.line_teacher_share = teacher
