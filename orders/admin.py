from django.contrib import admin
from orders.models import Order, OrderItem


class OrderItemTabularAdmin(admin.TabularInline):
    model = OrderItem
    fields = ("product", "name", "price", "quantity")
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product", "name", "price", "quantity")
    search_fields = ("name", "product__sku", "order__id")
    readonly_fields = (
        "order",
        "product",
        "name",
        "price",
        "quantity",
        "created_timestamp",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "requires_delivery",
        "status",
        "payment_on_get",
        "is_paid",
        "created_timestamp",
    )
    search_fields = ("=id", "first_name", "last_name", "user__username")
    readonly_fields = (
        "user",
        "checkout_token",
        "first_name",
        "last_name",
        "phone_number",
        "requires_delivery",
        "delivery_address",
        "payment_on_get",
        "created_timestamp",
    )
    list_filter = ("requires_delivery", "status", "payment_on_get", "is_paid")
    inlines = (OrderItemTabularAdmin,)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
