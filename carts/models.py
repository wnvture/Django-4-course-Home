from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

from goods.models import Products


class CartQueryset(models.QuerySet):
    def total_price(self):
        return sum((cart.products_price() for cart in self), Decimal("0.00"))

    def total_quantity(self):
        return sum(cart.quantity for cart in self)


class Cart(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        verbose_name="Пользователь",
    )
    product = models.ForeignKey(
        Products, on_delete=models.CASCADE, verbose_name="Товар"
    )
    quantity = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(32767)],
        verbose_name="Количество",
    )
    session_key = models.CharField(max_length=32, null=True, blank=True)
    created_timestamp = models.DateTimeField(
        auto_now_add=True, verbose_name="Дата добавления"
    )
    objects = CartQueryset.as_manager()

    class Meta:
        db_table = "cart"
        verbose_name = "Корзина"
        verbose_name_plural = "Корзины"
        ordering = ("id",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1, quantity__lte=32767),
                name="cart_quantity_range",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False, session_key__isnull=True)
                    | models.Q(user__isnull=True, session_key__isnull=False)
                    & ~models.Q(session_key="")
                ),
                name="cart_single_owner",
            ),
            models.UniqueConstraint(
                fields=["user", "product"],
                condition=models.Q(user__isnull=False),
                name="cart_user_product_unique",
            ),
            models.UniqueConstraint(
                fields=["session_key", "product"],
                condition=models.Q(user__isnull=True),
                name="cart_guest_product_unique",
            ),
        ]

    def products_price(self):
        return self.product.sell_price() * self.quantity

    def __str__(self):
        return f"{self.user or 'Гость'} · {self.product.name} × {self.quantity}"
