from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from users.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # Keep Django's password hashing, reset forms and permission controls.
    fieldsets = BaseUserAdmin.fieldsets + (("Изображение", {"fields": ("image",)}),)
    list_display = ("username", "first_name", "last_name", "email", "is_staff")
