from django.db.models import Sum

from .models import Product, ProductSize


def dashboard_callback(request, context):
    context.update(
        {
            "dashboard_products_count": Product.objects.count(),
            "dashboard_active_count": Product.objects.filter(
                is_available=True
            ).count(),
            "dashboard_stock_count": (
                ProductSize.objects.aggregate(total=Sum("quantity"))["total"] or 0
            ),
        }
    )
    return context
