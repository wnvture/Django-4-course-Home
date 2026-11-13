from django.contrib.auth import get_user_model
from django.db import transaction

from carts.models import Cart
from goods.models import Products


def get_user_carts(request):
    if request.user.is_authenticated:
        return Cart.objects.filter(user=request.user).select_related("product")
    if not request.session.session_key:
        return Cart.objects.none()
    return Cart.objects.filter(
        user__isnull=True, session_key=request.session.session_key
    ).select_related("product")


def lock_user(user):
    if user.is_authenticated:
        get_user_model().objects.select_for_update().get(pk=user.pk)


@transaction.atomic
def merge_guest_cart(user, session_key):
    if not session_key:
        return
    lock_user(user)
    guests = list(
        Cart.objects.filter(user__isnull=True, session_key=session_key).order_by(
            "product_id"
        )
    )
    list(
        Products.objects.select_for_update()
        .filter(pk__in=[g.product_id for g in guests])
        .order_by("pk")
    )
    for guest in guests:
        existing = Cart.objects.filter(user=user, product_id=guest.product_id).first()
        if existing:
            existing.quantity = min(existing.quantity + guest.quantity, 32767)
            existing.save(update_fields=["quantity"])
            guest.delete()
        else:
            guest.user = user
            guest.session_key = None
            guest.save(update_fields=["user", "session_key"])
