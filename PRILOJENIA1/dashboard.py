from django.db.models import Count, Q, Sum
from django.utils import timezone

from .admin import LOW_STOCK_LIMIT
from .models import Order, Product, ProductSize, RestockRequest, StockMovement


def dashboard_callback(request, context):
    today = timezone.now().date()
    orders_today = Order.objects.filter(created_at__date=today)

    status_counts = dict(
        Order.objects.values_list("status").annotate(total=Count("pk"))
    )
    revenue = Order.objects.exclude(status=Order.Status.CANCELLED).aggregate(
        total=Sum("total_price")
    )["total"] or 0
    revenue_today = (
        Order.objects.exclude(status=Order.Status.CANCELLED)
        .filter(created_at__date=today)
        .aggregate(total=Sum("total_price"))["total"]
        or 0
    )

    low_stocks = (
        ProductSize.objects.select_related("product", "store")
        .filter(quantity__lte=LOW_STOCK_LIMIT, product__is_available=True)
        .order_by("quantity", "product__name")
    )
    out_of_stock_count = ProductSize.objects.filter(quantity=0).count()
    low_stock_count = low_stocks.count()

    sold_total = (
        StockMovement.objects.filter(kind=StockMovement.Kind.SALE).aggregate(
            total=Sum("quantity")
        )["total"]
        or 0
    )

    context.update(
        {
            "dashboard_products_count": Product.objects.count(),
            "dashboard_active_count": Product.objects.filter(
                is_available=True
            ).count(),
            "dashboard_stock_count": (
                ProductSize.objects.aggregate(total=Sum("quantity"))["total"] or 0
            ),
            "dashboard_orders_count": Order.objects.count(),
            "dashboard_orders_new": status_counts.get(Order.Status.NEW, 0),
            "dashboard_orders_processing": status_counts.get(
                Order.Status.PROCESSING, 0
            ),
            "dashboard_orders_completed": status_counts.get(
                Order.Status.COMPLETED, 0
            ),
            "dashboard_orders_today": orders_today.count(),
            "dashboard_revenue": f"{revenue:,}".replace(",", " "),
            "dashboard_revenue_today": f"{revenue_today:,}".replace(",", " "),
            "dashboard_sold_total": abs(sold_total),
            "dashboard_low_stock_count": low_stock_count,
            "dashboard_out_of_stock_count": out_of_stock_count,
            "dashboard_low_stocks": low_stocks[:8],
            "dashboard_low_stock_limit": LOW_STOCK_LIMIT,
            "dashboard_restock_pending": RestockRequest.objects.count(),
            "dashboard_recent_orders": (
                Order.objects.select_related("store", "user")
                .prefetch_related("items")[:8]
            ),
            "dashboard_recent_movements": (
                StockMovement.objects.select_related(
                    "stock__product", "stock__store"
                )[:6]
            ),
        }
    )
    return context
