from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from goods.inventory_views import (
    InventoryView,
    ImportPreviewView,
    ImportApplyView,
    inventory_export,
    import_template,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("main.urls", namespace="main")),
    path("catalog/", include("goods.urls", namespace="catalog")),
    path("user/", include("users.urls", namespace="user")),
    path("cart/", include("carts.urls", namespace="cart")),
    path("orders/", include("orders.urls", namespace="orders")),
    path("inventory/", InventoryView.as_view(), name="inventory"),
    path("inventory/import/", ImportPreviewView.as_view(), name="import_preview"),
    path(
        "inventory/import/<uuid:pk>/apply/",
        ImportApplyView.as_view(),
        name="import_apply",
    ),
    path("inventory/export/", inventory_export, name="inventory_export"),
    path("inventory/template/", import_template, name="import_template"),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
admin.site.site_header = "HOME · управление магазином"
admin.site.site_title = "HOME Admin"
admin.site.index_title = "Товары, остатки и заказы"
