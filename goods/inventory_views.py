import csv
import io
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from goods.importing import (
    COLUMNS,
    MAX_BYTES,
    ImportValidationError,
    apply_import,
    prepare_import,
)
from goods.models import ProductImport, Products
from goods.utils import q_search


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class UploadForm(forms.Form):
    file = forms.FileField(
        label="CSV в UTF-8", widget=forms.FileInput(attrs={"accept": ".csv"})
    )

    def clean_file(self):
        file = self.cleaned_data["file"]
        if not file.name.lower().endswith(".csv") or file.size > MAX_BYTES:
            raise forms.ValidationError("Нужен CSV размером до 2 МБ.")
        return file


def threshold(request):
    try:
        return max(0, min(100000, int(request.GET.get("threshold", "3"))))
    except ValueError:
        return 3


class InventoryView(StaffRequiredMixin, View):
    def get(self, request):
        all_products = Products.objects.select_related("category").order_by("sku")
        products = q_search(request.GET.get("q", "")).order_by("sku")
        limit = threshold(request)
        if request.GET.get("low") == "on":
            products = products.filter(quantity__lte=limit)
        value = sum(
            (p.sell_price() * p.quantity for p in all_products), Decimal("0.00")
        )
        return render(
            request,
            "goods/inventory.html",
            {
                "title": "Остатки и импорт · HOME",
                "products": products,
                "product_count": all_products.count(),
                "units": all_products.aggregate(n=Sum("quantity"))["n"] or 0,
                "stock_value": value,
                "low_count": all_products.filter(quantity__lte=limit).count(),
                "threshold": limit,
                "form": UploadForm(),
                "batches": ProductImport.objects.select_related("created_by")[:10],
            },
        )


class ImportPreviewView(StaffRequiredMixin, View):
    def post(self, request):
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                file = form.cleaned_data["file"]
                batch = prepare_import(file.read(), file.name, request.user)
                return render(
                    request,
                    "goods/import_preview.html",
                    {"title": "Предпросмотр импорта · HOME", "batch": batch},
                )
            except ImportValidationError as exc:
                for error in exc.errors:
                    form.add_error("file", error)
        return render(
            request,
            "goods/import_error.html",
            {"title": "Проверка CSV · HOME", "form": form},
            status=400,
        )


class ImportApplyView(StaffRequiredMixin, View):
    def post(self, request, pk):
        get_object_or_404(ProductImport, pk=pk, created_by=request.user)
        try:
            batch = apply_import(pk, request.user)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(
                request,
                f"Импорт выполнен: создано {batch.summary['created']}, обновлено {batch.summary['updated']}.",
            )
        return redirect("inventory")


def csv_response(rows, filename):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=";")
    for row in rows:
        writer.writerow(
            [
                "'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@")) else v
                for v in row
            ]
        )
    response = HttpResponse(
        "\ufeff" + stream.getvalue(), content_type="text/csv; charset=utf-8"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def inventory_export(request):
    if not request.user.is_staff:
        raise PermissionDenied
    products = (
        q_search(request.GET.get("q", "")).select_related("category").order_by("sku")
    )
    if request.GET.get("low") == "on":
        products = products.filter(quantity__lte=threshold(request))
    rows = [
        [
            "sku",
            "name",
            "category",
            "quantity",
            "price_kzt",
            "discount_percent",
            "selling_price_kzt",
            "stock_value_kzt",
        ]
    ]
    rows += [
        [
            p.sku,
            p.name,
            p.category.name,
            p.quantity,
            p.price,
            p.discount,
            p.sell_price(),
            p.sell_price() * p.quantity,
        ]
        for p in products
    ]
    return csv_response(rows, "home-stock.csv")


@login_required
def import_template(request):
    if not request.user.is_staff:
        raise PermissionDenied
    return csv_response(
        [
            COLUMNS,
            [
                "HOME-NEW-001",
                "Учебный стул",
                "Офис",
                "24900.00",
                "10",
                "0",
                "Пример товара; замените значения перед импортом.",
            ],
        ],
        "products-template.csv",
    )
