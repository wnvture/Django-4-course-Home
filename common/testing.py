"""Small factories shared by the regression tests."""

from decimal import Decimal
from uuid import uuid4
from goods.models import Categories, Products
from users.models import User


def make_user(username="buyer", **kwargs):
    return User.objects.create_user(
        username=username,
        password="Furniture!4820",
        first_name="Дархан",
        last_name="Тест",
        email=f"{username}@example.com",
        **kwargs,
    )


def make_product(**kwargs):
    defaults = {
        "name": "Кресло",
        "price": Decimal("100.00"),
        "quantity": 5,
        "category": Categories.objects.get_or_create(name="Мебель")[0],
    }
    defaults.update(kwargs)
    return Products.objects.create(**defaults)


def order_data(**kwargs):
    data = {
        "first_name": "Дархан",
        "last_name": "Тест",
        "phone_number": "+77001234567",
        "requires_delivery": False,
        "delivery_address": "",
        "checkout_token": uuid4(),
    }
    data.update(kwargs)
    return data
