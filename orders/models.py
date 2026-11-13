from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.db import models

from goods.models import Products


class OrderitemQueryset(models.QuerySet):
    def total_price(self):
        return sum((item.products_price() for item in self), Decimal("0.00"))

    def total_quantity(self):
        return sum(item.quantity for item in self)


class Order(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name="Покупатель",
    )
    checkout_token = models.UUIDField(default=uuid4, unique=True, editable=False)
    first_name = models.CharField(
        max_length=150, blank=True, verbose_name="Имя покупателя"
    )
    last_name = models.CharField(
        max_length=150, blank=True, verbose_name="Фамилия покупателя"
    )
    created_timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    phone_number = models.CharField(max_length=20, verbose_name="Номер телефона")
    requires_delivery = models.BooleanField(
        default=False, verbose_name="Требуется доставка"
    )
    delivery_address = models.TextField(
        null=True, blank=True, verbose_name="Адрес доставки"
    )
    payment_on_get = models.BooleanField(
        default=True, verbose_name="Оплата при получении"
    )
    is_paid = models.BooleanField(default=False, verbose_name="Оплачено")
    status = models.CharField(
        max_length=50, default="В обработке", verbose_name="Статус"
    )

    class Meta:
        db_table = "order"
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ("-id",)

    def __str__(self):
        return f"Заказ № {self.pk} · {self.first_name} {self.last_name}".strip()


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, verbose_name="Заказ")
    product = models.ForeignKey(
        Products, on_delete=models.SET_NULL, null=True, verbose_name="Товар"
    )
    name = models.CharField(max_length=150, verbose_name="Название на момент заказа")
    price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Цена на момент заказа"
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name="Количество")
    created_timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    objects = OrderitemQueryset.as_manager()

    class Meta:
        db_table = "order_item"
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказов"
        ordering = ("id",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1, price__gte=0),
                name="order_item_valid_amounts",
            )
        ]

    def products_price(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.name} × {self.quantity} · заказ № {self.order_id}"
