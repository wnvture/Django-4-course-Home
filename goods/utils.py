from django.db import connection
from django.db.models import Func, Q, TextField

from goods.models import Products


def q_search(query):
    query = query.strip()[:200]
    products = Products.objects.select_related("category")
    if not query:
        return products
    if connection.vendor == "sqlite":
        products = products.annotate(
            search_name=Func(
                "name", function="UNICODE_CASEFOLD", output_field=TextField()
            ),
            search_description=Func(
                "description", function="UNICODE_CASEFOLD", output_field=TextField()
            ),
            search_sku=Func(
                "sku", function="UNICODE_CASEFOLD", output_field=TextField()
            ),
        )
        for token in query.casefold().split()[:10]:
            products = products.filter(
                Q(search_name__contains=token)
                | Q(search_description__contains=token)
                | Q(search_sku__contains=token)
            )
        return products
    for token in query.split()[:10]:
        products = products.filter(
            Q(name__icontains=token)
            | Q(description__icontains=token)
            | Q(sku__icontains=token)
        )
    return products
