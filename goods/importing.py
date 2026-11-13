"""Validate the complete import before writing; apply it once inside a transaction."""

import csv
import hashlib
import io
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify

from goods.models import Categories, ProductImport, Products

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1000
ALIASES = {
    "артикул": "sku",
    "наименование": "name",
    "название": "name",
    "категория": "category",
    "цена": "price",
    "остаток": "quantity",
    "количество": "quantity",
    "скидка": "discount",
    "описание": "description",
}
COLUMNS = ["sku", "name", "category", "price", "quantity", "discount", "description"]


class ImportValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("Исправьте ошибки в CSV и загрузите файл заново.")


def snapshot(product):
    if product is None:
        return None
    return {
        "id": product.pk,
        "name": product.name,
        "slug": product.slug,
        "category_id": product.category_id,
        "price": str(product.price),
        "discount": str(product.discount),
        "quantity": product.quantity,
        "description": product.description or "",
    }


def parse_csv(data):
    if len(data) > MAX_BYTES:
        raise ImportValidationError(["Файл должен быть не больше 2 МБ."])
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportValidationError(["Сохраните CSV в UTF-8."]) from exc
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t")
    except csv.Error:
        dialect = None
    reader = (
        csv.reader(io.StringIO(text), dialect, strict=True)
        if dialect
        else csv.reader(io.StringIO(text), delimiter=";", strict=True)
    )
    try:
        headers = [
            ALIASES.get(h.strip().casefold(), h.strip().casefold())
            for h in next(reader)
        ]
    except (StopIteration, csv.Error) as exc:
        raise ImportValidationError(["Файл пуст или заголовки повреждены."]) from exc
    if not {"sku", "name", "category", "price", "quantity"}.issubset(headers):
        raise ImportValidationError(
            ["Нужны столбцы sku, name, category, price, quantity."]
        )
    if (
        len(headers) != len(set(headers))
        or any(not h for h in headers)
        or len(headers) > 50
    ):
        raise ImportValidationError(
            ["Заголовки должны быть заполнены и не должны повторяться."]
        )
    rows, errors, seen_sku, seen_name = [], [], set(), set()
    try:
        for line, values in enumerate(reader, 2):
            if not any(v.strip() for v in values):
                continue
            if len(rows) >= MAX_ROWS:
                raise ImportValidationError(
                    [f"В файле допускается до {MAX_ROWS} товаров."]
                )
            if len(values) != len(headers):
                errors.append(
                    f"Строка {line}: число значений не совпадает с заголовками."
                )
                continue
            row = {k: v.strip() for k, v in zip(headers, values)}
            record = {k: row.get(k, "") for k in COLUMNS}
            record["line"] = line
            sku, name, category = record["sku"], record["name"], record["category"]
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", sku):
                errors.append(
                    f"Строка {line}: неверный артикул. Используйте латинские буквы, цифры, точку, дефис и подчёркивание."
                )
            if sku in seen_sku:
                errors.append(f"Строка {line}: артикул {sku} повторяется.")
            seen_sku.add(sku)
            if not name or len(name) > 150 or name in seen_name:
                errors.append(
                    f"Строка {line}: название должно быть уникальным в файле и содержать 1–150 символов."
                )
            seen_name.add(name)
            if (
                not category
                or len(category) > 150
                or category.casefold() in {"all", "все товары"}
            ):
                errors.append(
                    f"Строка {line}: укажите конкретную категорию до 150 символов."
                )
            for field, maximum in [
                ("price", Decimal("99999999.99")),
                ("discount", Decimal("100")),
            ]:
                try:
                    amount = Decimal(
                        record[field].replace(",", ".")
                        or ("0" if field == "discount" else "NaN")
                    )
                    if (
                        not amount.is_finite()
                        or not 0 <= amount <= maximum
                        or amount != amount.quantize(Decimal("0.01"))
                    ):
                        raise ValueError
                    record[field] = format(amount, ".2f")
                except (InvalidOperation, ValueError):
                    errors.append(
                        f"Строка {line}: {field} — число от 0 до {maximum}, не более 2 знаков после запятой."
                    )
            if (
                not re.fullmatch(r"[0-9]{1,10}", record["quantity"])
                or int(record["quantity"]) > 2147483647
            ):
                errors.append(
                    f"Строка {line}: остаток — целое число от 0 до 2147483647."
                )
            else:
                record["quantity"] = int(record["quantity"])
            if len(record["description"]) > 10000:
                errors.append(f"Строка {line}: описание длиннее 10000 символов.")
            rows.append(record)
    except csv.Error as exc:
        raise ImportValidationError(
            ["CSV повреждён. Проверьте кавычки и разделители."]
        ) from exc
    if not rows:
        errors.append("В файле нет товаров.")
    if errors:
        raise ImportValidationError(errors[:50])
    existing = {p.sku: p for p in Products.objects.filter(sku__in=seen_sku)}
    conflicting_names = {
        p.name: p.sku for p in Products.objects.filter(name__in=seen_name)
    }
    for row in rows:
        if (
            row["name"] in conflicting_names
            and conflicting_names[row["name"]] != row["sku"]
        ):
            errors.append(
                f"Строка {row['line']}: название уже используется другим артикулом."
            )
        current = existing.get(row["sku"])
        row["baseline"] = snapshot(current)
        row["slug"] = (
            current.slug
            if current and current.slug
            else (
                (slugify(row["name"], allow_unicode=True)[:120] or "item")
                + "-"
                + uuid4().hex[:10]
            )
        )
        row["action"] = "update" if current else "create"
    if errors:
        raise ImportValidationError(errors[:50])
    return rows


def prepare_import(data, filename, user):
    rows = parse_csv(data)
    return ProductImport.objects.create(
        created_by=user,
        filename=PurePosixPath(filename.replace("\\", "/")).name[:200],
        sha256=hashlib.sha256(data).hexdigest(),
        rows=rows,
        summary={
            "created": sum(r["action"] == "create" for r in rows),
            "updated": sum(r["action"] == "update" for r in rows),
            "rows": len(rows),
        },
    )


@transaction.atomic
def apply_import(batch_id, user):
    batch = ProductImport.objects.select_for_update().get(pk=batch_id, created_by=user)
    if batch.applied_at:
        return batch
    if timezone.now() - batch.created_at > timedelta(hours=24):
        raise ValidationError("Предпросмотр старше 24 часов. Загрузите файл заново.")
    current = {
        p.sku: p
        for p in Products.objects.select_for_update()
        .filter(sku__in=[r["sku"] for r in batch.rows])
        .order_by("pk")
    }
    for row in batch.rows:
        if snapshot(current.get(row["sku"])) != row["baseline"]:
            raise ValidationError(
                f"Товар {row['sku']} изменился после предпросмотра. Загрузите CSV заново."
            )
    try:
        # Nested savepoint keeps validation/uniqueness errors from leaving a partial import.
        with transaction.atomic():
            for row in batch.rows:
                category = Categories.objects.filter(name=row["category"]).first()
                if category is None:
                    category = Categories.objects.create(
                        name=row["category"],
                        slug=(
                            slugify(row["category"], allow_unicode=True)[:150]
                            or "category"
                        )
                        + "-"
                        + uuid4().hex[:8],
                    )
                product = current.get(row["sku"]) or Products(sku=row["sku"])
                for field in ("name", "slug", "description", "quantity"):
                    setattr(product, field, row[field])
                product.price = Decimal(row["price"])
                product.discount = Decimal(row["discount"])
                product.category = category
                product.full_clean()
                product.save()
            batch.applied_at = timezone.now()
            batch.save(update_fields=["applied_at"])
    except (IntegrityError, ValidationError) as exc:
        raise ValidationError(
            "Импорт отменён целиком: конфликт артикулов, названий или некорректные данные. Создайте новый предпросмотр."
        ) from exc
    return batch
