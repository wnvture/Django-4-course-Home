from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless

from django.core.exceptions import ValidationError
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from carts.models import Cart
from common.testing import make_product, make_user, order_data
from orders.forms import CreateOrderForm
from orders.models import Order, OrderItem
from orders.services import place_order
from users.models import User

FAST = override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)


@FAST
class CheckoutTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.product = make_product(
            price=Decimal("100"), discount=Decimal("10"), quantity=5
        )

    def test_empty_cart_does_not_create_order(self):
        with self.assertRaises(ValidationError):
            place_order(self.user, order_data())
        self.assertFalse(Order.objects.exists())
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(reverse("orders:create_order")).status_code, 200
        )

    def test_order_saves_discounted_price_decrements_stock_and_clears_cart(self):
        Cart.objects.create(user=self.user, product=self.product, quantity=2)
        order = place_order(self.user, order_data())
        item = order.orderitem_set.get()
        self.assertEqual(item.price, Decimal("90.00"))
        self.assertEqual(order.orderitem_set.total_price(), Decimal("180.00"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 3)
        self.assertFalse(Cart.objects.exists())

    def test_historical_order_survives_product_price_changes_and_deletion(self):
        Cart.objects.create(user=self.user, product=self.product, quantity=2)
        item = place_order(self.user, order_data()).orderitem_set.get()
        self.product.price = Decimal("999")
        self.product.save()
        item.refresh_from_db()
        self.assertEqual(item.products_price(), Decimal("180.00"))
        self.product.delete()
        item.refresh_from_db()
        self.assertIsNone(item.product_id)
        self.assertEqual(item.products_price(), Decimal("180.00"))

    def test_insufficient_stock_rolls_back_entire_order(self):
        second = make_product(name="Стол", quantity=0)
        Cart.objects.create(user=self.user, product=self.product, quantity=2)
        Cart.objects.create(user=self.user, product=second, quantity=1)
        with self.assertRaises(ValidationError):
            place_order(self.user, order_data())
        self.assertFalse(Order.objects.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 5)
        self.assertEqual(Cart.objects.count(), 2)

    def test_repeated_token_returns_same_order_without_consuming_new_cart(self):
        Cart.objects.create(user=self.user, product=self.product)
        data = order_data()
        first = place_order(self.user, data)
        Cart.objects.create(user=self.user, product=self.product)
        self.assertEqual(place_order(self.user, data).pk, first.pk)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Cart.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 4)

    def test_other_users_checkout_token_rejected(self):
        Cart.objects.create(user=self.user, product=self.product)
        data = order_data()
        place_order(self.user, data)
        with self.assertRaises(ValidationError):
            place_order(make_user("other"), data)

    def test_form_normalizes_phone_and_requires_delivery_address(self):
        for phone in ["8 (700) 123-45-67", "7001234567", "+7 700 123 45 67"]:
            data = order_data(phone_number=phone, requires_delivery="0")
            form = CreateOrderForm(data)
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data["phone_number"], "+77001234567")
        form = CreateOrderForm(order_data(requires_delivery="1"))
        self.assertFalse(form.is_valid())
        self.assertIn("delivery_address", form.errors)
        form = CreateOrderForm(order_data(phone_number="abc", requires_delivery="0"))
        self.assertFalse(form.is_valid())

    def test_checkout_http_flow_is_idempotent_and_profile_is_private(self):
        self.client.force_login(self.user)
        Cart.objects.create(user=self.user, product=self.product)
        response = self.client.get(reverse("orders:create_order"))
        token = response.context["form"].initial["checkout_token"]
        data = order_data(checkout_token=token, requires_delivery="0")
        for _ in range(2):
            self.assertRedirects(
                self.client.post(reverse("orders:create_order"), data),
                reverse("user:profile"),
            )
        self.assertEqual(Order.objects.count(), 1)
        self.client.force_login(make_user("stranger"))
        self.assertEqual(
            len(self.client.get(reverse("user:profile")).context["orders"]), 0
        )

    def test_unissued_checkout_token_does_not_place_order(self):
        self.client.force_login(self.user)
        Cart.objects.create(user=self.user, product=self.product)
        response = self.client.post(
            reverse("orders:create_order"), order_data(requires_delivery="0")
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())

    def test_checkout_requires_login(self):
        self.assertEqual(
            self.client.get(reverse("orders:create_order")).status_code, 302
        )


@skipUnless(
    connection.vendor == "postgresql",
    "Row-lock concurrency requires PostgreSQL; exercised in the PostgreSQL CI job.",
)
@FAST
class ConcurrentCheckoutTests(TransactionTestCase):
    def test_two_buyers_compete_for_last_unit(self):
        product = make_product(quantity=1)
        users = [make_user("buyer1"), make_user("buyer2")]
        for user in users:
            Cart.objects.create(user=user, product=product)
        barrier = Barrier(2)

        def checkout(user_id):
            try:
                user = User.objects.get(pk=user_id)
                barrier.wait(timeout=10)
                try:
                    place_order(user, order_data())
                    return "placed"
                except ValidationError:
                    return "out-of-stock"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(checkout, [u.pk for u in users]))
        self.assertCountEqual(results, ["placed", "out-of-stock"])
        product.refresh_from_db()
        self.assertEqual(product.quantity, 0)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.count(), 1)
