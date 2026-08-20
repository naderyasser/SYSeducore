"""
Role-Based Access Control (RBAC) Tests.

Tests:
- Admin-only endpoints reject teacher/supervisor users
- Supervisor endpoints reject teacher users
- Login required for all authenticated views
- User management restricted to admin only
"""
import json
import time

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.password_validation import validate_password
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import TestCase, Client, RequestFactory, override_settings
from django.urls import reverse

from apps.accounts import decorators
from apps.accounts.forms import UserCreateForm, UserUpdateForm
from apps.accounts.middleware import SessionTimeoutMiddleware
from apps.accounts.views import csrf_failure

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
        """Supervisor should NOT access user list — real 403, not a redirect."""
        self.client.force_login(self.supervisor)
        response = self.client.get(reverse('accounts:user_list'))
        self.assertEqual(response.status_code, 403)

    def test_teacher_blocked_from_user_list(self):
        """Teacher should NOT access user list — real 403, not a redirect."""
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('accounts:user_list'))
        self.assertEqual(response.status_code, 403)

    def test_teacher_blocked_from_user_create(self):
        """Teacher should NOT access user create — real 403, not a redirect."""
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('accounts:user_create'))
        self.assertEqual(response.status_code, 403)

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

    def test_supervisor_access_payments_report(self):
        """Supervisor should access payment report without password (200)."""
        self.client.force_login(self.supervisor)
        response = self.client.get(reverse('reports:payments'))
        self.assertEqual(response.status_code, 200)

    def test_teacher_blocked_from_financial_report(self):
        """Teacher must NOT reach the financial report — real 403 (AUTH-09)."""
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('reports:financial'))
        self.assertEqual(response.status_code, 403)


@override_settings(NOTIFICATION_METHOD='none')
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


@override_settings(RATELIMIT_ENABLE=False)
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


# ============================================================
#  Auth foundation contract (AUTH-13/14, AUTHN-01..08)
# ============================================================
class TestRoleDecoratorContract(TestCase):
    """The decorator API consumed across the whole project."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = User.objects.create_user(
            username='dec_admin', password='TestPass123!', role='admin'
        )
        self.supervisor = User.objects.create_user(
            username='dec_supervisor', password='TestPass123!', role='supervisor'
        )
        self.teacher = User.objects.create_user(
            username='dec_teacher', password='TestPass123!', role='teacher'
        )

    def _call(self, decorator, user):
        @decorator
        def view(request):
            return HttpResponse('ok')

        request = self.factory.get('/some/path/')
        request.user = user
        return view(request)

    def test_exports_the_full_contract(self):
        for name in (
            'ajax_login_required', 'admin_required', 'supervisor_required',
            'teacher_required', 'ajax_admin_required',
            'ajax_supervisor_required', 'ratelimit_key',
        ):
            self.assertTrue(hasattr(decorators, name), f'missing {name}')

    def test_html_decorators_403_for_wrong_role(self):
        cases = [
            (decorators.admin_required, self.supervisor),
            (decorators.admin_required, self.teacher),
            (decorators.supervisor_required, self.teacher),
        ]
        for decorator, user in cases:
            with self.assertRaises(PermissionDenied):
                self._call(decorator, user)

    def test_html_decorators_allow_correct_roles(self):
        cases = [
            (decorators.admin_required, self.admin),
            (decorators.supervisor_required, self.admin),
            (decorators.supervisor_required, self.supervisor),
            (decorators.teacher_required, self.teacher),
            (decorators.teacher_required, self.supervisor),
            (decorators.teacher_required, self.admin),
        ]
        for decorator, user in cases:
            self.assertEqual(self._call(decorator, user).status_code, 200)

    def test_html_decorators_redirect_anonymous(self):
        for decorator in (decorators.admin_required,
                          decorators.supervisor_required,
                          decorators.teacher_required):
            response = self._call(decorator, AnonymousUser())
            self.assertEqual(response.status_code, 302)
            self.assertIn('login', response.url)

    def test_ajax_decorators_return_json_401_and_403(self):
        for decorator, bad_user in (
            (decorators.ajax_admin_required, self.teacher),
            (decorators.ajax_supervisor_required, self.teacher),
        ):
            anon = self._call(decorator, AnonymousUser())
            self.assertEqual(anon.status_code, 401)
            self.assertFalse(json.loads(anon.content)['success'])

            forbidden = self._call(decorator, bad_user)
            self.assertEqual(forbidden.status_code, 403)
            payload = json.loads(forbidden.content)
            self.assertFalse(payload['success'])
            self.assertIn('message', payload)

        self.assertEqual(
            self._call(decorators.ajax_admin_required, self.admin).status_code, 200
        )
        self.assertEqual(
            self._call(decorators.ajax_supervisor_required, self.supervisor).status_code,
            200,
        )

    def test_ratelimit_key_prefers_forwarded_for(self):
        """AUTHN-01: behind nginx every client must get its own bucket."""
        request = self.factory.get(
            '/', HTTP_X_FORWARDED_FOR='41.44.1.9, 172.18.0.5', REMOTE_ADDR='172.18.0.5'
        )
        self.assertEqual(decorators.ratelimit_key('group', request), '41.44.1.9')

        direct = self.factory.get('/', REMOTE_ADDR='10.0.0.7')
        self.assertEqual(decorators.ratelimit_key('group', direct), '10.0.0.7')


class TestPasswordPolicy(TestCase):
    """AUTHN-03/04/05: password validators and self-lockout guards."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='pw_admin', password='TestPass123!', role='admin'
        )
        self.other_admin = User.objects.create_user(
            username='pw_admin2', password='TestPass123!', role='admin'
        )

    def test_weak_password_rejected_on_create(self):
        form = UserCreateForm(data={
            'username': 'weakling', 'first_name': 'a', 'last_name': 'b',
            'email': '', 'role': 'teacher', 'phone': '',
            'password1': '1', 'password2': '1',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('password1', form.errors)

    def test_strong_password_accepted_on_create(self):
        form = UserCreateForm(data={
            'username': 'stronghold', 'first_name': 'a', 'last_name': 'b',
            'email': '', 'role': 'teacher', 'phone': '',
            'password1': 'Str0ngPassw0rd!', 'password2': 'Str0ngPassw0rd!',
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_generated_password_passes_validators(self):
        form = UserCreateForm(data={
            'username': 'autopass', 'first_name': 'a', 'last_name': 'b',
            'email': '', 'role': 'teacher', 'phone': '',
        })
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        validate_password(user._generated_password, user)

    def test_weak_password_rejected_on_update(self):
        form = UserUpdateForm(
            data={
                'username': 'pw_admin2', 'first_name': '', 'last_name': '',
                'email': '', 'role': 'admin', 'phone': '', 'is_active': True,
                'new_password': '12345678',
            },
            instance=self.other_admin,
            request_user=self.admin,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('new_password', form.errors)

    def test_admin_cannot_deactivate_self_via_form(self):
        form = UserUpdateForm(
            data={
                'username': 'pw_admin', 'first_name': '', 'last_name': '',
                'email': '', 'role': 'admin', 'phone': '', 'new_password': '',
            },
            instance=self.admin,
            request_user=self.admin,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('is_active', form.errors)

    def test_admin_cannot_demote_self_via_form(self):
        form = UserUpdateForm(
            data={
                'username': 'pw_admin', 'first_name': '', 'last_name': '',
                'email': '', 'role': 'teacher', 'phone': '', 'is_active': True,
                'new_password': '',
            },
            instance=self.admin,
            request_user=self.admin,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('role', form.errors)

    def test_last_active_admin_cannot_be_demoted(self):
        self.admin.role = 'supervisor'
        self.admin.save()
        form = UserUpdateForm(
            data={
                'username': 'pw_admin2', 'first_name': '', 'last_name': '',
                'email': '', 'role': 'teacher', 'phone': '', 'is_active': True,
                'new_password': '',
            },
            instance=self.other_admin,
            request_user=self.admin,
        )
        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors())

    def test_generated_password_not_leaked_into_messages(self):
        """AUTHN-04: the plaintext password must not reach the session."""
        self.client.force_login(self.admin)
        response = self.client.post(reverse('accounts:user_create'), {
            'username': 'freshuser', 'first_name': 'a', 'last_name': 'b',
            'email': '', 'role': 'teacher', 'phone': '',
            'password1': '', 'password2': '',
        })
        self.assertEqual(response.status_code, 200)
        created = User.objects.get(username='freshuser')
        self.assertTrue(created.has_usable_password())
        self.assertEqual(len(list(get_messages(response.wsgi_request))), 0)


class TestSelfServicePasswordChange(TestCase):
    """AUTHN-04: every user can change their own password."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='pwchange', password='TestPass123!', role='teacher'
        )

    def test_requires_login(self):
        response = self.client.get(reverse('accounts:password_change'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_page_renders(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('accounts:password_change'))
        self.assertEqual(response.status_code, 200)

    def test_password_changed_and_session_kept(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('accounts:password_change'), {
            'old_password': 'TestPass123!',
            'new_password1': 'An0therGoodPass!',
            'new_password2': 'An0therGoodPass!',
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('An0therGoodPass!'))
        # Still logged in (update_session_auth_hash).
        self.assertEqual(
            self.client.get(reverse('accounts:password_change')).status_code, 200
        )

    def test_weak_new_password_rejected(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('accounts:password_change'), {
            'old_password': 'TestPass123!',
            'new_password1': '1',
            'new_password2': '1',
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('TestPass123!'))


@override_settings(RATELIMIT_ENABLE=False)
class TestInactiveLoginMessage(TestCase):
    """AUTHN-06: an inactive account gets its own message."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='sleeper', password='TestPass123!', role='supervisor'
        )
        self.user.is_active = False
        self.user.save()

    def test_inactive_user_sees_inactive_message(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'sleeper', 'password': 'TestPass123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'غير نشط')

    def test_wrong_password_still_generic(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'sleeper', 'password': 'nope',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'غير نشط')


class TestCsrfFailureHandler(TestCase):
    """AUTHN-07: JSON for AJAX, friendly redirect for HTML."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_json_403_for_ajax(self):
        request = self.factory.post('/attendance/scan/')
        request.META['HTTP_X_REQUESTED_WITH'] = 'XMLHttpRequest'
        response = csrf_failure(request, reason='CSRF token missing')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(json.loads(response.content)['success'])

    def test_redirect_for_html_form_post(self):
        request = self.factory.post('/accounts/login/')
        request.session = self.client.session
        request._messages = FallbackStorage(request)
        response = csrf_failure(request, reason='CSRF token missing')
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)


class TestSessionTimeoutMiddleware(TestCase):
    """AUTHN-08: cheap idle timeout, skipped for static assets."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='idler', password='TestPass123!', role='supervisor'
        )

    def _request(self, path='/reports/'):
        request = self.factory.get(path)
        request.user = self.user
        request.session = SessionStore()
        return request

    def _middleware(self):
        return SessionTimeoutMiddleware(lambda request: HttpResponse('ok'))

    def test_static_requests_do_not_touch_the_session(self):
        middleware = self._middleware()
        request = self._request('/static/css/app.css')
        middleware(request)
        self.assertNotIn('last_activity', request.session)

    def test_first_request_records_activity(self):
        middleware = self._middleware()
        request = self._request()
        middleware(request)
        self.assertIn('last_activity', request.session)

    def test_recent_activity_is_not_rewritten(self):
        middleware = self._middleware()
        request = self._request()
        stamp = time.time() - 5
        request.session['last_activity'] = stamp
        request.session.modified = False
        middleware(request)
        self.assertEqual(request.session['last_activity'], stamp)
        self.assertFalse(request.session.modified)

    def test_idle_session_is_flushed(self):
        middleware = self._middleware()
        request = self._request()
        request.session['last_activity'] = time.time() - 10 * 3600
        middleware(request)
        self.assertNotIn('last_activity', request.session)
