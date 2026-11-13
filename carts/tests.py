from django.test import TestCase, override_settings
from django.urls import reverse
from carts.models import Cart
from common.testing import make_product, make_user


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CartTests(TestCase):
    def setUp(self):
        self.product = make_product(quantity=2)
        self.ajax = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}

    def post(self, action, data):
        return self.client.post(reverse("cart:cart_" + action), data, **self.ajax)

    def test_first_guest_add_creates_persistent_cart_without_referer(self):
        self.assertEqual(
            self.post("add", {"product_id": self.product.pk}).status_code, 200
        )
        cart = Cart.objects.get()
        self.assertEqual(cart.session_key, self.client.session.session_key)
        self.assertIsNone(cart.user_id)
        self.assertContains(
            self.client.get(reverse("user:users_cart")), self.product.name
        )

    def test_stock_cannot_be_exceeded_by_add_or_update(self):
        self.post("add", {"product_id": self.product.pk})
        self.assertEqual(
            self.post(
                "change", {"cart_id": Cart.objects.get().pk, "quantity": 3}
            ).status_code,
            409,
        )
        self.post("add", {"product_id": self.product.pk})
        self.assertEqual(
            self.post("add", {"product_id": self.product.pk}).status_code, 409
        )
        self.assertEqual(Cart.objects.get().quantity, 2)

    def test_invalid_quantities_and_ids_rejected(self):
        self.post("add", {"product_id": self.product.pk})
        for quantity in ["0", "-1", "1.2", "32768", "x", ""]:
            with self.subTest(quantity=quantity):
                self.assertEqual(
                    self.post(
                        "change",
                        {"cart_id": Cart.objects.get().pk, "quantity": quantity},
                    ).status_code,
                    400,
                )
        self.assertEqual(self.post("add", {"product_id": "oops"}).status_code, 400)
        self.assertEqual(Cart.objects.get().quantity, 1)

    def test_other_users_cart_cannot_be_changed_or_deleted(self):
        owner = make_user("owner")
        self.client.force_login(make_user("stranger"))
        cart = Cart.objects.create(user=owner, product=self.product)
        for action in ["change", "remove"]:
            self.assertEqual(
                self.post(action, {"cart_id": cart.pk, "quantity": 1}).status_code, 404
            )
        self.assertTrue(Cart.objects.filter(pk=cart.pk).exists())

    def test_guest_cannot_see_another_session_cart(self):
        Cart.objects.create(session_key="another-session", product=self.product)
        self.assertEqual(
            self.client.get(reverse("user:users_cart")).context["carts"].count(), 0
        )

    def test_remove_own_item(self):
        self.post("add", {"product_id": self.product.pk})
        self.assertEqual(
            self.post("remove", {"cart_id": Cart.objects.get().pk}).json()[
                "cart_count"
            ],
            0,
        )
        self.assertFalse(Cart.objects.exists())

    def test_get_cannot_mutate_cart(self):
        self.assertEqual(
            self.client.get(
                reverse("cart:cart_add"), {"product_id": self.product.pk}
            ).status_code,
            405,
        )
        self.assertFalse(Cart.objects.exists())

    def test_form_redirect_does_not_leave_site(self):
        response = self.client.post(
            reverse("cart:cart_add"),
            {"product_id": self.product.pk, "next": "https://evil.example/"},
        )
        self.assertEqual(response.url, reverse("user:users_cart"))
