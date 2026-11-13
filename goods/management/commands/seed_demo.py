import json
import shutil
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection, transaction

from goods.models import Categories, Products


class Command(BaseCommand):
    help = "Load 12 fictional demo products into an empty database; does not create an admin account."

    @transaction.atomic
    def handle(self, *args, **options):
        if Products.objects.exists() or Categories.objects.exists():
            raise CommandError(
                "База уже содержит товары или категории. Команда не перезаписывает существующие данные."
            )
        root = settings.BASE_DIR
        categories = json.loads((root / "fixtures/goods/categories.json").read_text())
        for item in categories:
            if item["fields"]["slug"] != "all":
                Categories.objects.create(pk=item["pk"], **item["fields"])
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), [Categories]):
                cursor.execute(sql)
        prices = [
            129900,
            99900,
            229900,
            179900,
            199900,
            289900,
            34900,
            159900,
            39900,
            14900,
            9900,
            24900,
        ]
        originals = json.loads((root / "fixtures/goods/products.json").read_text())
        for item, price in zip(originals, prices):
            fields = item["fields"]
            image_name = fields["image"]
            source = (
                root
                / "static/deps/images/goods"
                / Path(image_name).name.replace("_", " ")
            )
            if source.exists():
                destination = settings.MEDIA_ROOT / image_name
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.exists():
                    shutil.copyfile(source, destination)
            Products.objects.create(
                sku=f"HOME-{item['pk']:05}",
                name=fields["name"],
                slug=fields["slug"],
                description=fields["description"],
                image=image_name if source.exists() else "",
                price=Decimal(price),
                discount=Decimal(fields["discount"]),
                quantity=fields["quantity"],
                category_id=fields["category"],
            )
        self.stdout.write(
            self.style.SUCCESS(
                "Готово: 12 товаров. Все цены и данные демонстрационные, цены указаны в ₸."
            )
        )
