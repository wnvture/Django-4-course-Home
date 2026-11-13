from django.urls import path

from goods import views

app_name = "goods"

urlpatterns = [
    path("search/", views.CatalogView.as_view(), name="search"),
    path("<str:category_slug>/", views.CatalogView.as_view(), name="index"),
    path("product/<str:product_slug>/", views.ProductView.as_view(), name="product"),
]
