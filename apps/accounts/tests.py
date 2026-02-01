"""
Comprehensive Unit Tests for Accounts App
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.accounts.models import User
from apps.accounts.forms import LoginForm

User = get_user_model()


class UserModelTestCase(TestCase):
    """Test User model"""
    
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='admin_test',
            email='admin@test.com',
            password='SecurePass123!',
            role='admin',
            first_name='Admin',
            last_name='User'
        )
        
        self.supervisor_user = User.objects.create_user(
            username='supervisor_test',
            email='supervisor@test.com',
            password='SecurePass123!',
            role='supervisor',
            first_name='Supervisor',
            last_name='User'
        )
        
        self.teacher_user = User.objects.create_user(
            username='teacher_test',
            email='teacher@test.com',
            password='SecurePass123!',
            role='teacher',
            first_name='Teacher',
            last_name='User'
        )
    
    def test_user_creation(self):
        """Test user is created correctly"""
        self.assertEqual(User.objects.count(), 3)
        self.assertEqual(self.admin_user.role, 'admin')
        self.assertTrue(self.admin_user.is_active)
    
    def test_user_string_representation(self):
        """Test __str__ method"""
        expected = f"{self.admin_user.get_full_name()} ({self.admin_user.get_role_display()})"
        self.assertEqual(str(self.admin_user), expected)
    
    def test_is_admin_method(self):
        """Test is_admin method"""
        self.assertTrue(self.admin_user.is_admin())
        self.assertFalse(self.supervisor_user.is_admin())
        self.assertFalse(self.teacher_user.is_admin())
    
    def test_is_supervisor_method(self):
        """Test is_supervisor method"""
        self.assertTrue(self.admin_user.is_supervisor())
        self.assertTrue(self.supervisor_user.is_supervisor())
        self.assertFalse(self.teacher_user.is_supervisor())
    
    def test_is_teacher_method(self):
        """Test is_teacher method"""
        self.assertFalse(self.admin_user.is_teacher())
        self.assertFalse(self.supervisor_user.is_teacher())
        self.assertTrue(self.teacher_user.is_teacher())
    
    def test_user_phone_field(self):
        """Test phone field"""
        self.admin_user.phone = '+201234567890'
        self.admin_user.save()
        self.assertEqual(self.admin_user.phone, '+201234567890')


class LoginViewTestCase(TestCase):
    """Test login view"""
    
    def setUp(self):
        self.client = Client()
        self.login_url = reverse('accounts:login')
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='SecurePass123!',
            role='supervisor'
        )
    
    def test_login_view_get(self):
        """Test GET request to login view"""
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'auth/login.html')
        self.assertIsInstance(response.context['form'], LoginForm)
    
    def test_login_view_successful_login(self):
        """Test successful login"""
        response = self.client.post(self.login_url, {
            'username': 'testuser',
            'password': 'SecurePass123!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('reports:dashboard'))
    
    def test_login_view_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = self.client.post(self.login_url, {
            'username': 'testuser',
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'اسم المستخدم أو كلمة المرور غير صحيحة')
    
    def test_login_view_inactive_user(self):
        """Test login with inactive user"""
        self.user.is_active = False
        self.user.save()
        response = self.client.post(self.login_url, {
            'username': 'testuser',
            'password': 'SecurePass123!'
        })
        self.assertEqual(response.status_code, 200)
        # Django returns generic error for inactive user
        self.assertContains(response, 'اسم المستخدم أو كلمة المرور غير صحيحة')
    
    def test_login_view_redirect_authenticated_user(self):
        """Test redirect for already authenticated user"""
        self.client.login(username='testuser', password='SecurePass123!')
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('reports:dashboard'))


class LogoutViewTestCase(TestCase):
    """Test logout view"""
    
    def setUp(self):
        self.client = Client()
        self.logout_url = reverse('accounts:logout')
        self.user = User.objects.create_user(
            username='testuser',
            password='SecurePass123!'
        )
    
    def test_logout_view(self):
        """Test logout functionality"""
        self.client.login(username='testuser', password='SecurePass123!')
        response = self.client.get(self.logout_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('accounts:login'))
    
    def test_logout_view_unauthenticated(self):
        """Test logout view requires authentication"""
        response = self.client.get(self.logout_url)
        self.assertEqual(response.status_code, 302)


class LoginFormTestCase(TestCase):
    """Test LoginForm"""
    
    def test_valid_form(self):
        """Test form with valid data"""
        form = LoginForm(data={
            'username': 'testuser',
            'password': 'SecurePass123!'
        })
        self.assertTrue(form.is_valid())
    
    def test_empty_username(self):
        """Test form with empty username"""
        form = LoginForm(data={
            'username': '',
            'password': 'SecurePass123!'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)
    
    def test_empty_password(self):
        """Test form with empty password"""
        form = LoginForm(data={
            'username': 'testuser',
            'password': ''
        })
        self.assertFalse(form.is_valid())
        self.assertIn('password', form.errors)
