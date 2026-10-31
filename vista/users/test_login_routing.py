from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from .models import User
from .serializers import UserSerializer
from organizations.models import Organization


class FirstLoginRoutingTests(TestCase):
    @patch('users.views.log_login')
    def test_first_login_flag_is_true_only_once_for_staff_and_students(self, _log):
        client = APIClient()
        for role in ('staff', 'student'):
            with self.subTest(role=role):
                user = User.objects.create_user(email=f'{role}@example.com', first_name='Test', last_name='User', role=role, password='test-password-123')
                credentials = {'email': user.email, 'password': 'test-password-123'}
                first = client.post(reverse('auth-login'), credentials, format='json')
                self.assertEqual(first.status_code, 200, first.data)
                self.assertTrue(first.data['is_first_login'])
                second = client.post(reverse('auth-login'), credentials, format='json')
                self.assertFalse(second.data['is_first_login'])

    def test_profile_includes_organization_logo(self):
        org = Organization.objects.create(name='Test Organization', acronym='TEST', image_url='https://example.com/logo.webp')
        user = User.objects.create_user(email='logo@example.com', first_name='Test', last_name='User', org_id=org)
        self.assertEqual(UserSerializer(user).data['org_image_url'], org.image_url)
