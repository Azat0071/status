"""Общие данные для шаблонов: точки продаж, корзина и заказы покупателя."""

from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.middleware.csrf import get_token
from django.urls import reverse

from .checkout import attach_checkout_groups
from .models import Store

EXCHANGE_RATES = {"KGS": 1, "USD": 0.011, "EUR": 0.010}


def store_context(request):
    stores = list(
        Store.objects.filter(is_active=True).annotate(
            positions=Coalesce(Sum("sizes__quantity"), 0)
        )
    )
    current_store = getattr(request, "store", None) or Store.default()
    is_authenticated = request.user.is_authenticated
    customer_orders = (
        attach_checkout_groups(
            request.user.orders.prefetch_related("items").select_related("store").all()
        )
        if is_authenticated
        else ()
    )
    cart_context = {
        "currentStoreId": current_store.pk if current_store else None,
        "isAuthenticated": is_authenticated,
        "csrfToken": get_token(request),
        "rates": EXCHANGE_RATES,
        "stores": [
            {"id": store.pk, "name": store.name, "address": store.address}
            for store in stores
        ],
        "urls": {
            "validate": reverse("validate_cart"),
            "createOrder": reverse("create_order"),
            "login": reverse("login"),
        },
    }
    return {
        "stores": stores,
        "current_store": current_store,
        "customer_orders": customer_orders,
        "cart_context": cart_context,
    }
