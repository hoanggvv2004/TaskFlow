from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="an.nguyen",
            email="an@example.com",
            password="Secret123",
            first_name="Nguyen Van An",
            role=User.Role.MEMBER,
        )

    def test_login_with_username(self):
        response = self.client.post(reverse("accounts:login"), {"username": "an.nguyen", "password": "Secret123"})
        self.assertEqual(response.status_code, 302)

    def test_login_with_email(self):
        response = self.client.post(reverse("accounts:login"), {"username": "an@example.com", "password": "Secret123"})
        self.assertEqual(response.status_code, 302)

    def test_login_rejects_bad_password(self):
        response = self.client.post(reverse("accounts:login"), {"username": "an.nguyen", "password": "wrongpass"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "không đúng")

    def test_locked_user_cannot_login(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(reverse("accounts:login"), {"username": "an.nguyen", "password": "Secret123"})
        self.assertEqual(response.status_code, 200)
