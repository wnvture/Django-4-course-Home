from django.contrib import admin
from goods.models import Categories, ProductImport, Products


@admin.register(Categories)
class CategoriesAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}
    list_display = ("name", "slug")


@admin.register(Products)
class ProductsAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}
    list_display = ("sku", "name", "quantity", "price", "discount")
    search_fields = ("sku", "name", "description")
    list_filter = ("category",)
    fields = (
        "sku",
        "name",
        "category",
        "slug",
        "description",
        "image",
        ("price", "discount"),
        "quantity",
    )


@admin.register(ProductImport)
class ProductImportAdmin(admin.ModelAdmin):
    list_display = ("filename", "created_by", "created_at", "applied_at")
    readonly_fields = (
        "id",
        "created_by",
        "created_at",
        "applied_at",
        "filename",
        "sha256",
        "rows",
        "summary",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
