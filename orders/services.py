from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from carts.models import Cart
from carts.utils import lock_user
from goods.models import Products
from orders.models import Order, OrderItem


@transaction.atomic
def place_order(user, data):
    lock_user(user)
    previous = Order.objects.filter(checkout_token=data["checkout_token"]).first()
    if previous:
        if previous.user_id != user.pk:
            raise ValidationError("Обновите страницу оформления заказа.")
        return previous
    carts = list(Cart.objects.filter(user=user).order_by("product_id"))
    if not carts:
        raise ValidationError("Корзина пуста. Сначала добавьте товары.")
    products = {
        p.pk: p
        for p in Products.objects.select_for_update()
        .filter(pk__in=[c.product_id for c in carts])
        .order_by("pk")
    }
    for cart in carts:
        product = products.get(cart.product_id)
        if not product or not 1 <= cart.quantity <= product.quantity:
            raise ValidationError(
                f"Для товара «{product.name if product else 'Удалённый товар'}» недостаточно остатка."
            )
    order = Order.objects.create(
        user=user,
        checkout_token=data["checkout_token"],
        first_name=data["first_name"],
        last_name=data["last_name"],
        phone_number=data["phone_number"],
        requires_delivery=data["requires_delivery"],
        delivery_address=data["delivery_address"],
        payment_on_get=True,
    )
    for cart in carts:
        product = products[cart.product_id]
        changed = Products.objects.filter(
            pk=product.pk, quantity__gte=cart.quantity
        ).update(quantity=F("quantity") - cart.quantity)
        if changed != 1:
            raise ValidationError(
                "Остатки изменились. Проверьте корзину и повторите заказ."
            )
        OrderItem.objects.create(
            order=order,
            product=product,
            name=product.name,
            price=product.sell_price(),
            quantity=cart.quantity,
        )
    Cart.objects.filter(pk__in=[c.pk for c in carts]).delete()
    return order
