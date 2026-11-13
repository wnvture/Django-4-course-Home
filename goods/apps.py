from django.apps import AppConfig
from django.db.backends.signals import connection_created


def enable_unicode_search(sender, connection, **kwargs):
    if connection.vendor == "sqlite":
        connection.connection.create_function(
            "UNICODE_CASEFOLD", 1, lambda v: (v or "").casefold(), deterministic=True
        )


class GoodsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "goods"
    verbose_name = "Товары"

    def ready(self):
        connection_created.connect(
            enable_unicode_search, dispatch_uid="home_unicode_search"
        )
