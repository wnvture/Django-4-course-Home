import re
from django import forms


class CreateOrderForm(forms.Form):
    first_name = forms.CharField(max_length=150, label="Имя")
    last_name = forms.CharField(max_length=150, label="Фамилия")
    phone_number = forms.CharField(
        max_length=30,
        label="Телефон",
        widget=forms.TextInput(
            attrs={"type": "tel", "placeholder": "+7 700 123 45 67"}
        ),
    )
    requires_delivery = forms.TypedChoiceField(
        choices=[("0", "Самовывоз"), ("1", "Доставка")],
        coerce=lambda v: v == "1",
        label="Получение заказа",
        widget=forms.RadioSelect,
    )
    delivery_address = forms.CharField(
        max_length=1000,
        required=False,
        label="Адрес доставки",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    checkout_token = forms.UUIDField(widget=forms.HiddenInput)

    def clean_phone_number(self):
        value = self.cleaned_data["phone_number"].strip()
        if re.search(r"[^0-9+() -]", value):
            raise forms.ValidationError(
                "Введите телефон цифрами, например +7 700 123 45 67."
            )
        digits = re.sub(r"[^0-9]", "", value)
        if len(digits) == 10:
            digits = "7" + digits
        elif len(digits) == 11 and digits.startswith("8"):
            digits = "7" + digits[1:]
        if len(digits) != 11 or not digits.startswith("7"):
            raise forms.ValidationError("Нужен номер из 11 цифр с кодом +7.")
        return "+" + digits

    def clean(self):
        data = super().clean()
        if data.get("requires_delivery") and not data.get("delivery_address"):
            self.add_error("delivery_address", "Укажите адрес для доставки.")
        if not data.get("requires_delivery"):
            data["delivery_address"] = ""
        return data
