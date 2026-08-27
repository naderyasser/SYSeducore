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
    
    def is_admin(self):
        return self.role == 'admin'

    def is_supervisor(self):
        return self.role in ['admin', 'supervisor']

    def is_teacher(self):
        return self.role == 'teacher'

    def can_see_financials(self):
        """
        Cumulative money — total revenue, centre dues, collection rate.
        Admin only.

        ``is_admin()`` misses a superuser whose ``role`` is still the
        default ``'supervisor'``: they pass every ``@admin_required`` view
        but ``is_admin()`` says False, so templates gated on it disagree
        with what the view actually allows. Views and templates must both
        gate on this method (not ``role == 'admin'`` directly) so the two
        can never diverge.
        """
        return bool(self.is_superuser or self.role == 'admin')

    def can_collect_payments(self):
        """Day-to-day desk collection (per-payment, not aggregates) — admin or supervisor."""
        return bool(self.is_superuser or self.role in ('admin', 'supervisor'))
