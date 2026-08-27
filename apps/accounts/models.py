from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom User Model with role-based access control.
    """
    ROLE_CHOICES = [
        ('admin', 'مدير النظام'),
        ('supervisor', 'مشرف الحضور'),
        ('teacher', 'مدرس'),
    ]
    
    user_id = models.AutoField(primary_key=True)
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='supervisor',
        verbose_name='الدور'
    )
    phone = models.CharField(
        max_length=17,
        blank=True,
        verbose_name='رقم الهاتف'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'users'
        verbose_name = 'مستخدم'
        verbose_name_plural = 'المستخدمين'
    
    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"
    
    # ── Role predicates ──────────────────────────────────────────────
    # A superuser counts as admin regardless of ``role``: they already pass
    # every ``@admin_required`` view (``decorators._has_role`` short-circuits
    # on ``is_superuser``), so a predicate that read ``role`` alone made the
    # templates disagree with what the views actually allow — a superuser
    # left on the default ``'supervisor'`` role got the admin's access but
    # the supervisor's menu. Views and templates must both gate on these
    # methods, never on ``role == '...'`` directly.

    def is_admin(self):
        return bool(self.is_superuser or self.role == 'admin')

    def is_supervisor(self):
        """Desk staff — reception/attendance supervisor, or an admin above them."""
        return bool(self.is_superuser or self.role in ('admin', 'supervisor'))

    def is_teacher(self):
        return self.role == 'teacher'

    def can_see_financials(self):
        """Cumulative money — total revenue, centre dues, collection rate."""
        return self.is_admin()

    def can_collect_payments(self):
        """Day-to-day desk collection (per-payment, never aggregates)."""
        return self.is_supervisor()
