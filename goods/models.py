from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


def generate_sku():
    return "HOME-" + uuid4().hex[:12].upper()


class Categories(models.Model):
    name = models.CharField(max_length=150, unique=True, verbose_name="Название")
    slug = models.SlugField(
        max_length=200,
        unique=True,
        blank=True,
        null=True,
        allow_unicode=True,
        verbose_name="URL",
    )

    class Meta:
        db_table = "category"
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ("id",)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = (
                (slugify(self.name, allow_unicode=True)[:150] or "category")
                + "-"
                + uuid4().hex[:10]
            )
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"slug"}
        super().save(*args, **kwargs)


class Products(models.Model):
    sku = models.CharField(
        max_length=64,
        unique=True,
        default=generate_sku,
        verbose_name="Артикул",
        validators=[
            RegexValidator(
                r"^[A-Za-z0-9][A-Za-z0-9_.-]*$",
                "Артикул: латинские буквы, цифры, точка, дефис и подчёркивание.",
            )
        ],
    )
    name = models.CharField(max_length=150, unique=True, verbose_name="Название")
    slug = models.SlugField(
        max_length=200,
        unique=True,
        blank=True,
        null=True,
        allow_unicode=True,
        verbose_name="URL",
    )
    description = models.TextField(blank=True, null=True, verbose_name="Описание")
    image = models.ImageField(
        upload_to="goods_images", blank=True, null=True, verbose_name="Изображение"
    )
    price = models.DecimalField(
        default=0,
        max_digits=10,
        decimal_places=2,
        verbose_name="Цена, ₸",
        validators=[MinValueValidator(0)],
    )
    discount = models.DecimalField(
        default=0,
        max_digits=5,
        decimal_places=2,
        verbose_name="Скидка, %",
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    quantity = models.PositiveIntegerField(default=0, verbose_name="Остаток")
    category = models.ForeignKey(
        Categories, on_delete=models.PROTECT, verbose_name="Категория"
    )

    class Meta:
        db_table = "product"
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ("id",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gte=0), name="product_price_nonnegative"
            ),
            models.CheckConstraint(
                condition=models.Q(discount__gte=0, discount__lte=100),
                name="product_discount_range",
            ),
        ]

    def __str__(self):
        return f"{self.sku} · {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = (
                (slugify(self.name, allow_unicode=True)[:150] or "item")
                + "-"
                + uuid4().hex[:10]
            )
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"slug"}
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("catalog:product", kwargs={"product_slug": self.slug})

    def display_id(self):
        return self.sku

    def sell_price(self):
        return (self.price * (Decimal("1") - self.discount / 100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


class ProductImport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    filename = models.CharField(max_length=200)
    sha256 = models.CharField(max_length=64)
    rows = models.JSONField(default=list)
    summary = models.JSONField(default=dict)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Импорт товаров"
        verbose_name_plural = "Импорты товаров"
