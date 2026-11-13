from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView, UpdateView

from carts.utils import get_user_carts, merge_guest_cart
from orders.models import Order
from users.forms import ProfileForm, UserLoginForm, UserRegistrationForm


class UserLoginView(LoginView):
    template_name = "users/login.html"
    form_class = UserLoginForm

    def form_valid(self, form):
        session_key = self.request.session.session_key
        response = super().form_valid(form)
        merge_guest_cart(self.request.user, session_key)
        messages.success(self.request, "Вы вошли в аккаунт.")
        return response


class UserRegistrationView(CreateView):
    template_name = "users/registration.html"
    form_class = UserRegistrationForm
    success_url = reverse_lazy("user:profile")

    def form_valid(self, form):
        session_key = self.request.session.session_key
        response = super().form_valid(form)
        merge_guest_cart(self.object, session_key)
        login(self.request, self.object)
        messages.success(self.request, "Аккаунт создан. Товары из корзины сохранены.")
        return response


class UserProfileView(LoginRequiredMixin, UpdateView):
    template_name = "users/profile.html"
    form_class = ProfileForm
    success_url = reverse_lazy("user:profile")

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, "Профиль обновлён.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            title="Личный кабинет · HOME",
            orders=Order.objects.filter(user=self.request.user).prefetch_related(
                "orderitem_set"
            ),
        )
        return context


class UserCartView(TemplateView):
    template_name = "users/users_cart.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(title="Корзина · HOME", carts=get_user_carts(self.request))
        return context


class UserLogoutView(LogoutView):
    next_page = reverse_lazy("main:index")
