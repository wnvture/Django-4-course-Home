import csv
import io
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from common.testing import make_product, make_user
from goods.importing import (
    MAX_BYTES,
    ImportValidationError,
    apply_import,
    parse_csv,
    prepare_import,
)
from goods.models import Categories, ProductImport, Products

FAST = override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)


def csv_data(*rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=";")
    writer.writerow(
        ["sku", "name", "category", "price", "quantity", "discount", "description"]
    )
    writer.writerows(
        rows or [["SKU-1", "Стул", "Офис", "125.50", "3", "10", "Описание"]]
    )
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


class CatalogTests(TestCase):
    def test_empty_catalog_and_home_are_available(self):
        for url in [
            reverse("main:index"),
            reverse("catalog:index", args=["all"]),
            reverse("catalog:search"),
        ]:
            self.assertEqual(self.client.get(url).status_code, 200)
        self.assertNotIn("sessionid", self.client.cookies)

    def test_unicode_search_matches_all_words_and_sku(self):
        target = make_product(
            name="Кресло мягкое", description="Зелёное", sku="CHAIR-42"
        )
        make_product(name="Стол", description="Зелёный")
        for term in ["КРЕСЛО мягкое", "кресло ЗЕЛЁНОЕ", "chair-42"]:
            response = self.client.get(reverse("catalog:search"), {"q": term})
            self.assertEqual(list(response.context["goods"]), [target])

    def test_sort_uses_discounted_price_and_rejects_arbitrary_fields(self):
        expensive = make_product(
            name="Дорогое", price=Decimal("150"), discount=Decimal("80")
        )
        ordinary = make_product(name="Обычное", price=Decimal("50"))
        response = self.client.get(
            reverse("catalog:index", args=["all"]), {"order_by": "price"}
        )
        self.assertEqual(list(response.context["goods"]), [expensive, ordinary])
        self.assertEqual(
            self.client.get(
                reverse("catalog:search"), {"order_by": "not-a-field"}
            ).status_code,
            200,
        )

    def test_missing_image_and_unicode_slug_render(self):
        product = make_product(name="Светильник")
        self.assertTrue(product.slug)
        self.assertEqual(self.client.get(product.get_absolute_url()).status_code, 200)
        self.assertEqual(
            self.client.get(
                reverse("catalog:index", args=[product.category.slug])
            ).status_code,
            200,
        )

    def test_user_supplied_html_is_escaped(self):
        product = make_product(
            name="<script>alert(1)</script>", description="<img src=x onerror=alert(2)>"
        )
        response = self.client.get(product.get_absolute_url())
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertNotContains(response, "<img src=x onerror=alert(2)>")

    def test_unknown_category_or_product_is_404(self):
        self.assertEqual(
            self.client.get(reverse("catalog:index", args=["missing"])).status_code, 404
        )
        self.assertEqual(
            self.client.get(reverse("catalog:product", args=["missing"])).status_code,
            404,
        )

    def test_discount_rounds_half_up(self):
        self.assertEqual(
            make_product(price=Decimal("0.05"), discount=Decimal("50")).sell_price(),
            Decimal("0.03"),
        )


@FAST
class ImportTests(TestCase):
    def setUp(self):
        self.staff = make_user("manager", is_staff=True)

    def test_preview_does_not_change_stock_and_apply_is_idempotent(self):
        batch = prepare_import(csv_data(), "../../products.csv", self.staff)
        self.assertEqual(batch.filename, "products.csv")
        self.assertFalse(Products.objects.exists())
        apply_import(batch.pk, self.staff)
        apply_import(batch.pk, self.staff)
        self.assertEqual(Products.objects.count(), 1)
        self.assertEqual(Products.objects.get().price, Decimal("125.50"))
        self.assertIsNotNone(ProductImport.objects.get().applied_at)

    def test_existing_sku_updates_without_changing_slug_or_image(self):
        item = make_product(sku="SKU-1", image="goods_images/old.jpg")
        old_slug = item.slug
        apply_import(prepare_import(csv_data(), "x.csv", self.staff).pk, self.staff)
        item.refresh_from_db()
        self.assertEqual(
            (item.quantity, item.name, item.slug, item.image.name),
            (3, "Стул", old_slug, "goods_images/old.jpg"),
        )

    def test_invalid_rows_cause_no_writes(self):
        for row in [
            ["A", "X", "Y", "-1", "2", "0", ""],
            ["A", "X", "Y", "NaN", "2", "0", ""],
            ["A", "X", "Y", "1.001", "2", "0", ""],
            ["A", "X", "Y", "1", "-1", "0", ""],
            ["A", "X", "Y", "1", "2", "101", ""],
            ["bad sku", "X", "Y", "1", "2", "0", ""],
        ]:
            with self.subTest(row=row), self.assertRaises(ImportValidationError):
                prepare_import(csv_data(row), "x.csv", self.staff)
        self.assertFalse(ProductImport.objects.exists())
        self.assertFalse(Products.objects.exists())

    def test_duplicate_skus_and_names_rejected(self):
        for second in [
            ["SKU-1", "Другое", "Офис", "1", "2", "0", ""],
            ["SKU-2", "Стул", "Офис", "1", "2", "0", ""],
        ]:
            with self.subTest(second=second), self.assertRaises(ImportValidationError):
                parse_csv(
                    csv_data(["SKU-1", "Стул", "Офис", "1", "2", "0", ""], second)
                )

    def test_wrong_encoding_empty_oversize_and_missing_headers_rejected(self):
        for data in [
            b"",
            "Артикул".encode("cp1251"),
            b"x" * (MAX_BYTES + 1),
            b"name;price\nx;1",
        ]:
            with (
                self.subTest(length=len(data)),
                self.assertRaises(ImportValidationError),
            ):
                parse_csv(data)

    def test_russian_headers_and_decimal_comma(self):
        data = "Артикул;Название;Категория;Цена;Остаток\nA;Стул;Офис;123,45;2".encode()
        self.assertEqual(parse_csv(data)[0]["price"], "123.45")

    def test_existing_other_sku_name_collision_rejected(self):
        make_product(name="Стул", sku="OTHER")
        with self.assertRaises(ImportValidationError):
            parse_csv(csv_data())

    def test_stale_preview_cannot_overwrite_sale(self):
        item = make_product(sku="SKU-1")
        batch = prepare_import(csv_data(), "x.csv", self.staff)
        Products.objects.filter(pk=item.pk).update(quantity=4)
        with self.assertRaises(ValidationError):
            apply_import(batch.pk, self.staff)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 4)
        self.assertIsNone(ProductImport.objects.get().applied_at)

    def test_expired_preview_rejected(self):
        batch = prepare_import(csv_data(), "x.csv", self.staff)
        ProductImport.objects.filter(pk=batch.pk).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        with self.assertRaises(ValidationError):
            apply_import(batch.pk, self.staff)
        self.assertFalse(Products.objects.exists())

    def test_import_rolls_back_every_row_if_later_row_fails(self):
        batch = prepare_import(
            csv_data(
                ["SKU-1", "Первый", "Новая", "10", "1", "0", ""],
                ["SKU-2", "Второй", "Новая", "10", "1", "0", ""],
            ),
            "x.csv",
            self.staff,
        )
        original = Products.full_clean

        def validate(product, *args, **kwargs):
            if product.sku == "SKU-2":
                raise ValidationError("Conflict")
            return original(product, *args, **kwargs)

        with (
            patch.object(Products, "full_clean", validate),
            self.assertRaises(ValidationError),
        ):
            apply_import(batch.pk, self.staff)
        self.assertFalse(Products.objects.exists())
        self.assertFalse(Categories.objects.exists())
        self.assertIsNone(ProductImport.objects.get().applied_at)

    def test_staff_only_and_batch_owner_only(self):
        for url in [
            reverse("inventory"),
            reverse("inventory_export"),
            reverse("import_template"),
        ]:
            self.assertEqual(self.client.get(url).status_code, 302)
        user = make_user("ordinary")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("inventory")).status_code, 403)
        self.assertEqual(self.client.get(reverse("inventory_export")).status_code, 403)
        self.assertEqual(self.client.post(reverse("import_preview")).status_code, 403)
        batch = prepare_import(csv_data(), "x.csv", self.staff)
        self.client.force_login(make_user("other", is_staff=True))
        self.assertEqual(
            self.client.post(reverse("import_apply", args=[batch.pk])).status_code, 404
        )

    def test_preview_apply_and_dashboard_through_http(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("import_preview"),
            {"file": SimpleUploadedFile("test.csv", csv_data())},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Products.objects.exists())
        batch = response.context["batch"]
        self.assertRedirects(
            self.client.post(reverse("import_apply", args=[batch.pk])),
            reverse("inventory"),
        )
        response = self.client.get(reverse("inventory"))
        self.assertEqual(response.context["units"], 3)
        self.assertEqual(response.context["stock_value"], Decimal("338.85"))

    def test_export_escapes_spreadsheet_formulas_and_filters(self):
        make_product(name='=HYPERLINK("x")', sku="A", quantity=1)
        make_product(name="Обычный", sku="B", quantity=10)
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("inventory_export"), {"low": "on", "threshold": "3"}
        )
        rows = list(
            csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";")
        )
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[1][1].startswith("'="))
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")

    def test_import_endpoints_require_post(self):
        self.client.force_login(self.staff)
        batch = prepare_import(csv_data(), "x.csv", self.staff)
        self.assertEqual(self.client.get(reverse("import_preview")).status_code, 405)
        self.assertEqual(
            self.client.get(reverse("import_apply", args=[batch.pk])).status_code, 405
        )


class DemoSeedTests(TestCase):
    def test_demo_seed_and_new_category_sequence(self):
        import tempfile

        with (
            tempfile.TemporaryDirectory() as directory,
            override_settings(MEDIA_ROOT=directory),
        ):
            # Production MEDIA_ROOT is a Path; make the override match it.
            from pathlib import Path

            with override_settings(MEDIA_ROOT=Path(directory)):
                call_command("seed_demo", stdout=io.StringIO())
            self.assertEqual(Products.objects.count(), 12)
            self.assertTrue(Categories.objects.create(name="Новая").pk)
            with self.assertRaises(CommandError):
                call_command("seed_demo", stdout=io.StringIO())
