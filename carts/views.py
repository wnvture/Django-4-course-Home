from django import forms
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from carts.models import Cart
from carts.utils import get_user_carts, lock_user
from goods.models import Products


class CartInput(forms.Form):
    product_id = forms.IntegerField(min_value=1, required=False)
    cart_id = forms.IntegerField(min_value=1, required=False)
    quantity = forms.IntegerField(min_value=1, max_value=32767, required=False)


class CartAction(View):
    def response(self, request, message, status=200):
        carts = get_user_carts(request)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "message": message,
                    "cart_count": carts.total_quantity(),
                    "cart_items_html": render_to_string(
                        "carts/includes/included_cart.html",
                        {"carts": carts},
                        request=request,
                    ),
                },
                status=status,
            )
        (messages.error if status >= 400 else messages.success)(request, message)
        target = request.POST.get("next") or request.META.get("HTTP_REFERER", "")
        if not url_has_allowed_host_and_scheme(
            target,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            target = reverse("user:users_cart")
        return redirect(target)

    def post(self, request):
        form = CartInput(request.POST)
        if not form.is_valid():
            return self.response(
                request, "Проверьте идентификатор и количество товара.", 400
            )
        with transaction.atomic():
            lock_user(request.user)
            if self.action == "add":
                if not form.cleaned_data["product_id"]:
                    return self.response(request, "Не указан товар.", 400)
                product = get_object_or_404(
                    Products.objects.select_for_update(),
                    pk=form.cleaned_data["product_id"],
                )
                if (
                    not request.user.is_authenticated
                    and not request.session.session_key
                ):
                    request.session.create()
                owner = (
                    {"user": request.user, "session_key": None}
                    if request.user.is_authenticated
                    else {"user": None, "session_key": request.session.session_key}
                )
                cart = Cart.objects.filter(product=product, **owner).first()
                quantity = (cart.quantity if cart else 0) + 1
                if quantity > product.quantity or quantity > 32767:
                    return self.response(
                        request, "Больше этого товара сейчас нет в наличии.", 409
                    )
                if cart:
                    cart.quantity = quantity
                    cart.save(update_fields=["quantity"])
                else:
                    Cart.objects.create(product=product, quantity=1, **owner)
                return self.response(request, "Товар добавлен в корзину.")
            if not form.cleaned_data["cart_id"]:
                return self.response(request, "Не указана позиция корзины.", 400)
            owned = (
                get_user_carts(request).filter(pk=form.cleaned_data["cart_id"]).first()
            )
            if owned is None:
                return self.response(request, "Позиция корзины не найдена.", 404)
            product = get_object_or_404(
                Products.objects.select_for_update(), pk=owned.product_id
            )
            cart = get_object_or_404(Cart, pk=owned.pk)
            if self.action == "remove":
                cart.delete()
                return self.response(request, "Товар удалён из корзины.")
            quantity = form.cleaned_data["quantity"]
            if quantity is None:
                return self.response(request, "Укажите количество товара.", 400)
            if quantity > product.quantity:
                return self.response(
                    request, f"В наличии только {product.quantity} шт.", 409
                )
            cart.quantity = quantity
            cart.save(update_fields=["quantity"])
            return self.response(request, "Количество обновлено.")


class CartAddView(CartAction):
    action = "add"


class CartChangeView(CartAction):
    action = "change"


class CartRemoveView(CartAction):
    action = "remove"
