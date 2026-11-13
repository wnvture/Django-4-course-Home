from carts.utils import get_user_carts
from goods.models import Categories


def shop_context(request):
    return {
        "shop_categories": Categories.objects.exclude(slug="all"),
        "cart_count": get_user_carts(request).total_quantity(),
    }
