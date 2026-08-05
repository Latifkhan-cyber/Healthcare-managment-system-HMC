from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from backend.apps.accounts.models import User


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

    def test_admin_can_create_doctor_with_photo(self):
        admin = User.objects.create_superuser(username='admin', password='admin123', role='ADMIN')
        self.client.force_login(admin)

        response = self.client.post(reverse('create_staff'), {
            'username': 'dr_test',
            'email': 'drtest@clinic.com',
            'phone': '03001234567',
            'first_name': 'Test',
            'last_name': 'Doctor',
            'gender': 'MALE',
            'role': 'DOCTOR',
            'specialization': 'Cardiology',
            'consultation_fee': '1500',
            'password1': 'staff123',
            'password2': 'staff123',
        })

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('manage_staff'))
        doctor = User.objects.get(username='dr_test')
        self.assertEqual(doctor.role, 'DOCTOR')
        self.assertTrue(doctor.profile_photo)

    def test_admin_can_update_staff_photo(self):
        admin = User.objects.create_superuser(username='admin', password='admin123', role='ADMIN')
        doctor = User.objects.create_user(
            username='dr_update', password='staff123', role='DOCTOR',
            first_name='Update', last_name='Doctor', gender='MALE'
        )
        self.client.force_login(admin)

        photo = SimpleUploadedFile(
            'photo.jpg', b'fake-image-bytes', content_type='image/jpeg'
        )
        response = self.client.post(
            reverse('edit_staff', kwargs={'user_id': doctor.id}),
            {
                'first_name': 'Update',
                'last_name': 'Doctor',
                'email': 'update@clinic.com',
                'phone': '03001234567',
                'gender': 'MALE',
                'specialization': 'Cardiology',
                'consultation_fee': '2000',
            },
            format='multipart',
            **{'FILES': {'profile_photo': photo}}
        )

        self.assertEqual(response.status_code, 302)
        doctor.refresh_from_db()
        self.assertTrue(doctor.profile_photo)
