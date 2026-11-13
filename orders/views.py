from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.views.generic import FormView

from carts.utils import get_user_carts
from orders.forms import CreateOrderForm
from orders.models import Order
from orders.services import place_order


class CreateOrderView(LoginRequiredMixin, FormView):
    template_name = "orders/create_order.html"
    form_class = CreateOrderForm

    def get_initial(self):
        token = self.request.session.setdefault("checkout_token", str(uuid4()))
        return {
            "first_name": self.request.user.first_name,
            "last_name": self.request.user.last_name,
            "requires_delivery": "0",
            "checkout_token": token,
        }

    def form_valid(self, form):
        token = form.cleaned_data["checkout_token"]
        previous = Order.objects.filter(
            user=self.request.user, checkout_token=token
        ).exists()
        if not previous and str(token) != self.request.session.get("checkout_token"):
            form.add_error(None, "Срок формы истёк. Обновите страницу оформления.")
            return self.form_invalid(form)
        try:
            order = place_order(self.request.user, form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        self.request.session.pop("checkout_token", None)
        messages.success(
            self.request, f"Учебный заказ № {order.pk} сохранён. Оплата при получении."
        )
        return redirect("user:profile")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            title="Оформление заказа · HOME",
            carts=get_user_carts(self.request),
            checkout=True,
        )
        return context
