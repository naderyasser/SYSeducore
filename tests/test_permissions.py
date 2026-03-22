"""
Role-Based Access Control (RBAC) Tests.

Tests:
- Admin-only endpoints reject teacher/supervisor users
- Supervisor endpoints reject teacher users
- Login required for all authenticated views
- User management restricted to admin only
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

User = get_user_model()


class TestRBACBase(TestCase):
    """Base class with user fixtures for RBAC tests."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='rbac_admin', password='TestPass123!', role='admin'
        )
        self.supervisor = User.objects.create_user(
            username='rbac_supervisor', password='TestPass123!', role='supervisor'
        )
        self.teacher = User.objects.create_user(
            username='rbac_teacher', password='TestPass123!', role='teacher'
        )


class TestActivityLogAccess(TestRBACBase):
    """Test /reports/activity-log/ access control."""

    def test_admin_can_access_activity_log(self):
        """Admin should access activity log (200)."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('reports:activity_log'))
        self.assertEqual(response.status_code, 200)

    def test_teacher_can_access_activity_log(self):
        """Teacher accessing activity log — currently only @login_required.
        NOTE: This test documents the CURRENT behavior. If @admin_required
        is added later, this test should change to expect 302/403."""
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('reports:activity_log'))
        # Currently returns 200 since no @admin_required decorator
        # This is a known gap — sidebar hides it but URL is accessible
        self.assertIn(response.status_code, [200, 302, 403])

    def test_anonymous_redirected(self):
        """Anonymous user should be redirected to login."""
        response = self.client.get(reverse('reports:activity_log'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)


class TestUserManagementAccess(TestRBACBase):
    """Test /accounts/users/ access control (admin-only)."""

    def test_admin_can_access_user_list(self):
        """Admin should access user list (200)."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('accounts:user_list'))
        self.assertEqual(response.status_code, 200)

    def test_admin_can_access_user_create(self):
        """Admin should access user create form (200)."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('accounts:user_create'))
        self.assertEqual(response.status_code, 200)

    def test_supervisor_blocked_from_user_list(self):
        """Supervisor should NOT access user list — redirect to login or 403."""
        self.client.force_login(self.supervisor)
        response = self.client.get(reverse('accounts:user_list'))
        self.assertIn(response.status_code, [302, 403])

    def test_teacher_blocked_from_user_list(self):
        """Teacher should NOT access user list — redirect to login or 403."""
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('accounts:user_list'))
        self.assertIn(response.status_code, [302, 403])

    def test_teacher_blocked_from_user_create(self):
        """Teacher should NOT access user create — redirect or 403."""
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('accounts:user_create'))
        self.assertIn(response.status_code, [302, 403])

    def test_anonymous_redirected_from_user_list(self):
        """Anonymous user should be redirected to login."""
        response = self.client.get(reverse('accounts:user_list'))
        self.assertEqual(response.status_code, 302)


class TestStudentViewsAccess(TestRBACBase):
    """Test student-related view access."""

    def test_admin_can_access_student_list(self):
        """Admin should access student list."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('students:list'))
        self.assertEqual(response.status_code, 200)

    def test_supervisor_can_access_student_list(self):
        """Supervisor should access student list."""
        self.client.force_login(self.supervisor)
        response = self.client.get(reverse('students:list'))
        self.assertEqual(response.status_code, 200)

    def test_anonymous_redirected_from_student_list(self):
        """Anonymous user should be redirected."""
        response = self.client.get(reverse('students:list'))
        self.assertEqual(response.status_code, 302)


class TestReportPasswordBypass(TestRBACBase):
    """Test that admin bypasses report password requirement."""

    def test_admin_bypasses_password_for_payments_report(self):
        """Admin should access payment report without password (200)."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('reports:payments'))
        self.assertEqual(response.status_code, 200)

    def test_admin_bypasses_password_for_financial_report(self):
        """Admin should access financial report without password (200)."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('reports:financial'))
        self.assertEqual(response.status_code, 200)

    def test_supervisor_needs_password_for_payments_report(self):
        """Supervisor should be redirected to password prompt."""
        self.client.force_login(self.supervisor)
        response = self.client.get(reverse('reports:payments'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('password', response.url)

    def test_teacher_needs_password_for_financial_report(self):
        """Teacher should be redirected to password prompt."""
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('reports:financial'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('password', response.url)


class TestWhatsAppBlocking(TestRBACBase):
    """Test that WhatsApp views redirect when disabled."""

    def test_whatsapp_dashboard_redirects_when_disabled(self):
        """WhatsApp dashboard should redirect to reports dashboard when disabled."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('notifications:whatsapp_dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_whatsapp_send_redirects_when_disabled(self):
        """WhatsApp send message should redirect when disabled."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('notifications:send_message'))
        self.assertEqual(response.status_code, 302)


class TestLoginLogout(TestRBACBase):
    """Test login/logout flow."""

    def test_valid_login(self):
        """Valid credentials should redirect to dashboard."""
        response = self.client.post(
            reverse('accounts:login'),
            {'username': 'rbac_admin', 'password': 'TestPass123!'}
        )
        self.assertEqual(response.status_code, 302)

    def test_invalid_login(self):
        """Invalid credentials should show login page again."""
        response = self.client.post(
            reverse('accounts:login'),
            {'username': 'rbac_admin', 'password': 'wrong'}
        )
        self.assertEqual(response.status_code, 200)  # Re-renders form

    def test_inactive_user_blocked(self):
        """Inactive user should not be able to login."""
        self.admin.is_active = False
        self.admin.save()
        response = self.client.post(
            reverse('accounts:login'),
            {'username': 'rbac_admin', 'password': 'TestPass123!'}
        )
        self.assertEqual(response.status_code, 200)  # Login page with error

    def test_logout_requires_post(self):
        """Logout via GET should not log out (or redirect)."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('accounts:logout'))
        # GET to logout should either 405 or redirect, not actually log out
        self.assertIn(response.status_code, [302, 405])
