from django.db.models import DecimalField, ExpressionWrapper, F
from django.db.models.functions import Round
from django.shortcuts import get_object_or_404
from django.views.generic import DetailView, ListView

from goods.models import Categories, Products
from goods.utils import q_search


class CatalogView(ListView):
    model = Products
    template_name = "goods/catalog.html"
    context_object_name = "goods"
    paginate_by = 9
    allow_empty = True

    def get_queryset(self):
        query = self.request.GET.get("q", "")
        products = q_search(query)
        slug = self.kwargs.get("category_slug", "all")
        if slug != "all":
            self.category = get_object_or_404(Categories, slug=slug)
            products = products.filter(category=self.category)
        if self.request.GET.get("on_sale") == "on":
            products = products.filter(discount__gt=0)
        if self.request.GET.get("in_stock") == "on":
            products = products.filter(quantity__gt=0)
        products = products.annotate(
            effective_price=Round(
                ExpressionWrapper(
                    F("price") * (1 - F("discount") / 100.0),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                2,
            )
        )
        order = self.request.GET.get("order_by", "default")
        ordering = {
            "price": "effective_price",
            "-price": "-effective_price",
            "name": "name",
        }.get(order, "id")
        return products.order_by(ordering, "id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            title="Каталог · HOME",
            slug_url=self.kwargs.get("category_slug", "all"),
            category=getattr(self, "category", None),
        )
        return context


class ProductView(DetailView):
    model = Products
    template_name = "goods/product.html"
    slug_url_kwarg = "product_slug"
    context_object_name = "product"

    def get_queryset(self):
        return Products.objects.select_related("category")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"{self.object.name} · HOME"
        return context
