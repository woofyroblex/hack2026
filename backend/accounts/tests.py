from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient


class AuthIntegrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_registration_creates_customer_and_refresh_cookie_rotates(self):
        response = self.client.post("/api/v1/auth/register/", {
            "full_name": "Sample Customer",
            "email": "sample@example.com",
            "password": "SecurePass!9",
        }, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["role"], "customer")
        self.assertTrue(hasattr(get_user_model().objects.get(email="sample@example.com"), "customer_profile"))
        self.assertTrue(response.cookies["refresh_token"]["httponly"])
        first_refresh = response.cookies["refresh_token"].value

        self.client.cookies["refresh_token"] = first_refresh
        refreshed = self.client.post("/api/v1/auth/refresh/", {}, format="json")

        self.assertEqual(refreshed.status_code, 200)
        self.assertNotEqual(refreshed.cookies["refresh_token"].value, first_refresh)

    def test_registration_rejects_short_or_weak_password(self):
        response = self.client.post("/api/v1/auth/register/", {
            "full_name": "Weak Customer",
            "email": "weak@example.com",
            "password": "weakpass1",
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data["fields"])


class AccountSecurityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('secure', email='secure@example.com', password='SecurePass!9')
        self.client = APIClient(enforce_csrf_checks=True)

    def test_refresh_requires_csrf(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        from accounts.authentication import password_stamp
        token = RefreshToken.for_user(self.user)
        token['password_stamp'] = password_stamp(self.user)
        self.client.cookies['refresh_token'] = str(token)
        self.assertEqual(self.client.post('/api/v1/auth/refresh/', {}, format='json').status_code, 403)
        response = self.client.get('/api/v1/auth/csrf/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post('/api/v1/auth/refresh/', {}, format='json',
            HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value).status_code, 200)

    def test_password_reset_is_single_use_and_revokes_access(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        from accounts.views import _issue_tokens
        access = _issue_tokens(self.user).data['access_token']
        payload = {'uid': urlsafe_base64_encode(force_bytes(self.user.pk)),
                   'token': default_token_generator.make_token(self.user), 'password': 'ChangedSecure!9'}
        response = self.client.post('/api/v1/auth/password-reset/confirm/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post('/api/v1/auth/password-reset/confirm/', payload, format='json').status_code, 400)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + access)
        self.assertEqual(self.client.get('/api/v1/me/').status_code, 401)

    def test_reset_does_not_disclose_account(self):
        from unittest.mock import patch
        with patch('accounts.recovery.queue_email') as queue:
            existing = self.client.post('/api/v1/auth/password-reset/', {'email': self.user.email})
            missing = self.client.post('/api/v1/auth/password-reset/', {'email': 'missing@example.com'})
        self.assertEqual(existing.status_code, 202)
        self.assertEqual(existing.data, missing.data)
        self.assertEqual(queue.call_count, 1)
