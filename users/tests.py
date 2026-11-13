from django.test import Client, TestCase, override_settings
from django.urls import reverse
from carts.models import Cart
from common.testing import make_product, make_user
from users.models import User


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AccountTests(TestCase):
    def registration(self, **kwargs):
        data = {
            "first_name": "Дархан",
            "last_name": "Тест",
            "username": "newbuyer",
            "email": "buyer@example.com",
            "password1": "Furniture!4820",
            "password2": "Furniture!4820",
        }
        data.update(kwargs)
        return self.client.post(reverse("user:registration"), data)

    def test_registration_logs_in_and_preserves_guest_cart(self):
        item = make_product()
        self.client.post(reverse("cart:cart_add"), {"product_id": item.pk})
        old_session = self.client.session.session_key
        response = self.registration()
        self.assertRedirects(response, reverse("user:profile"))
        user = User.objects.get(username="newbuyer")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertEqual(Cart.objects.get().user_id, user.pk)
        self.assertIsNone(Cart.objects.get().session_key)
        self.assertNotEqual(old_session, self.client.session.session_key)

    def test_weak_password_and_mismatch_are_rejected_without_echoing(self):
        for fields in [
            {"password1": "123", "password2": "123"},
            {"password2": "DoesNotMatch!"},
        ]:
            response = self.registration(**fields)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(User.objects.exists())
            self.assertNotContains(response, 'value="Furniture!4820"')

    def test_login_merges_guest_cart_with_existing_items(self):
        user = make_user()
        item = make_product()
        Cart.objects.create(user=user, product=item, quantity=2)
        self.client.post(reverse("cart:cart_add"), {"product_id": item.pk})
        response = self.client.post(
            reverse("user:login"),
            {
                "username": user.username,
                "password": "Furniture!4820",
                "next": reverse("user:profile"),
            },
        )
        self.assertRedirects(response, reverse("user:profile"))
        self.assertEqual(Cart.objects.count(), 1)
        self.assertEqual(Cart.objects.get().quantity, 3)

    def test_login_rejects_external_redirect(self):
        user = make_user()
        response = self.client.post(
            reverse("user:login"),
            {
                "username": user.username,
                "password": "Furniture!4820",
                "next": "https://evil.example/",
            },
        )
        self.assertEqual(response.url, reverse("main:index"))

    def test_profile_requires_login_and_ignores_privilege_fields(self):
        self.assertEqual(self.client.get(reverse("user:profile")).status_code, 302)
        user = make_user()
        self.client.force_login(user)
        response = self.client.post(
            reverse("user:profile"),
            {
                "first_name": "Новое",
                "last_name": "Имя",
                "username": user.username,
                "email": user.email,
                "is_staff": "on",
                "is_superuser": "on",
                "password": "bad",
            },
        )
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Новое")
        self.assertFalse(user.is_staff)
        self.assertTrue(user.check_password("Furniture!4820"))

    def test_logout_requires_post(self):
        self.client.force_login(make_user())
        self.assertEqual(self.client.get(reverse("user:logout")).status_code, 405)
        self.assertEqual(self.client.post(reverse("user:logout")).status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_csrf_blocks_cart_and_login_without_token(self):
        browser = Client(enforce_csrf_checks=True)
        for url in ["cart:cart_add", "user:login"]:
            self.assertEqual(browser.post(reverse(url), {}).status_code, 403)

    def test_admin_user_creation_hashes_password(self):
        self.client.force_login(make_user("admin", is_staff=True, is_superuser=True))
        response = self.client.post(
            reverse("admin:users_user_add"),
            {
                "username": "admin-created",
                "password1": "Furniture!4820",
                "password2": "Furniture!4820",
                "usable_password": "true",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            User.objects.get(username="admin-created").check_password("Furniture!4820")
        )
