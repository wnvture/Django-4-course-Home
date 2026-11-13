from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from users.models import User


class UserLoginForm(AuthenticationForm):
    pass


class UserRegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, label="Имя")
    last_name = forms.CharField(max_length=150, label="Фамилия")
    email = forms.EmailField(label="Email")

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "username",
            "email",
            "password1",
            "password2",
        )


class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, label="Имя")
    last_name = forms.CharField(max_length=150, label="Фамилия")
    email = forms.EmailField(label="Email")

    class Meta:
        model = User
        fields = ("first_name", "last_name", "username", "email", "image")
        labels = {"image": "Аватар"}

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and hasattr(image, "content_type"):
            if image.size > 3 * 1024 * 1024:
                raise forms.ValidationError("Аватар должен быть меньше 3 МБ.")
            if (
                image.image.format not in {"JPEG", "PNG", "WEBP"}
                or image.image.width * image.image.height > 16_000_000
            ):
                raise forms.ValidationError(
                    "Используйте JPG, PNG или WebP размером до 16 мегапикселей."
                )
        return image
