"""Exercise upgrading populated tutorial databases, not only a fresh install."""

from decimal import Decimal
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class LegacyMigrationTests(TransactionTestCase):
    def test_existing_products_orders_and_duplicate_carts_are_preserved(self):
        old = [
            ("goods", "0003_alter_categories_options"),
            ("carts", "0002_alter_cart_options"),
            ("orders", "0002_alter_order_options_alter_orderitem_options"),
        ]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(old)
        try:
            apps = executor.loader.project_state(old).apps
            Category = apps.get_model("goods", "Categories")
            Product = apps.get_model("goods", "Products")
            User = apps.get_model("users", "User")
            Cart = apps.get_model("carts", "Cart")
            Order = apps.get_model("orders", "Order")
            Item = apps.get_model("orders", "OrderItem")
            user = User.objects.create(username="legacy")
            category = Category.objects.create(name="Старая категория", slug=None)
            products = [
                Product.objects.create(
                    name=f"Товар {i}",
                    price="100.00",
                    quantity=10,
                    category=category,
                    slug=None,
                )
                for i in range(2)
            ]
            for product in products:
                order = Order.objects.create(user=user, phone_number="+77001234567")
                Item.objects.create(
                    order=order,
                    product=product,
                    name=product.name,
                    price="25.00",
                    quantity=2,
                )
            Cart.objects.create(
                user=user, session_key="legacy", product=products[0], quantity=2
            )
            Cart.objects.create(
                user=user, session_key="other", product=products[0], quantity=3
            )
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            from goods.models import Categories, Products
            from carts.models import Cart as CurrentCart
            from orders.models import Order as CurrentOrder, OrderItem

            self.assertEqual(Products.objects.count(), 2)
            self.assertEqual(
                len(set(Products.objects.values_list("sku", flat=True))), 2
            )
            self.assertTrue(all(Products.objects.values_list("slug", flat=True)))
            self.assertTrue(Categories.objects.get().slug)
            self.assertEqual(
                len(set(CurrentOrder.objects.values_list("checkout_token", flat=True))),
                2,
            )
            self.assertEqual(CurrentCart.objects.get().quantity, 5)
            self.assertIsNone(CurrentCart.objects.get().session_key)
            self.assertEqual(OrderItem.objects.total_price(), Decimal("100.00"))
        finally:
            MigrationExecutor(connection).migrate(latest)
