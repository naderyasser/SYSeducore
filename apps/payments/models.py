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
    return amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


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
    sessions_attended = models.PositiveIntegerField(default=0, verbose_name="عدد الحصص المحضورة")
    sessions_total = models.PositiveIntegerField(default=4, verbose_name="إجمالي الحصص في الشهر")
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
        unique_together = ['student', 'group', 'month']
        ordering = ['-month']

    def __str__(self):
        return f"{self.student.full_name} - {self.group.group_name} - {self.month.strftime('%Y-%m')}"

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
    def record_transaction(self, amount, user=None, note='', kind=None, allow_reversal=False):
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

        Returns the created :class:`PaymentTransaction`, or ``None`` for a
        zero-amount no-op. Raises :class:`PaymentAmountError` — Arabic
        message — on any rejection.
        """
        amount = to_money(amount)

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
            )

        # Apply the already-known total: re-reading the ledger through
        # ``sync_ledger`` here would see the (now stale) ``amount_paid`` of
        # the locked row and "restore" a reversal as an opening balance.
        locked._apply_ledger_total(new_total)

        # Mirror the reconciled state onto the caller's instance.
        self.amount_paid = locked.amount_paid
        self.status = locked.status
        self.payment_date = locked.payment_date
        return txn

    @transaction.atomic
    def settle_full(self, user=None, note=''):
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
