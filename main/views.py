from django.views.generic import TemplateView
from goods.models import Categories, Products


class IndexView(TemplateView):
    template_name = "main/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            title="HOME · вещи для жизни",
            featured=Products.objects.select_related("category")
            .filter(quantity__gt=0)
            .order_by("id")[:6],
            categories=Categories.objects.exclude(slug="all"),
        )
        return context


class AboutView(TemplateView):
    template_name = "main/about.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "О проекте · HOME"
        return context
