from django.test import TestCase
from django.urls import reverse


class LoginFlowTests(TestCase):
    def test_login_creates_default_admin_when_no_user_exists(self):
        response = self.client.post(reverse('login'), {
            'username': 'admin',
            'password': 'admin123',
        })

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertTrue(response.wsgi_request.user.is_superuser)
