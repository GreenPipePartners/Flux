from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class InitialSetupTests(TestCase):
    def test_home_redirects_to_setup_when_no_users_exist(self):
        response = self.client.get(reverse("dashboard:home"))

        self.assertRedirects(response, reverse("dashboard:setup"))

    def test_setup_creates_initial_superuser(self):
        response = self.client.post(
            reverse("dashboard:setup"),
            {
                "username": "admin",
                "email": "admin@example.com",
                "password1": "long-test-password-123",
                "password2": "long-test-password-123",
            },
        )

        self.assertRedirects(response, reverse("admin:index"))
        user = get_user_model().objects.get(username="admin")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_setup_redirects_when_user_already_exists(self):
        get_user_model().objects.create_user(username="existing", password="test-pass")

        response = self.client.get(reverse("dashboard:setup"))

        self.assertRedirects(response, reverse("dashboard:home"))
