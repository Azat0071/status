"""Остатки по точкам продаж: выборки и расчёты для витрины."""

from collections import defaultdict

from .models import Product, Store

CLOTHING_SIZE_ORDER = ("XS", "S", "M", "L", "XL", "XXL", "ONE SIZE")


def active_stores():
    return list(Store.objects.filter(is_active=True))


def _size_key(name):
    size = name.strip().upper()
    if size in CLOTHING_SIZE_ORDER:
        return (0, CLOTHING_SIZE_ORDER.index(size), "")
    if size.isdigit():
        return (1, int(size), "")
    return (2, 0, size)


def sort_sizes(sizes):
    """Размеры в привычном порядке: XS→XXL, затем числовые, затем прочие."""
    return sorted(sizes, key=lambda stock: _size_key(stock.size))


def _sizes_by_store(product):
    grouped = defaultdict(list)
    for stock in product.sizes.all():
        grouped[stock.store_id].append(stock)
    return grouped


def _total(sizes):
    return sum(stock.quantity for stock in sizes)


def stock_map(grouped):
    """Остатки товара по точкам в виде, удобном для корзины в браузере."""
    result = {}
    for store_id, sizes in grouped.items():
        ordered = sort_sizes(sizes)
        result[str(store_id)] = {
            "total": _total(ordered),
            "sizes": [
                {"size": stock.size, "quantity": stock.quantity}
                for stock in ordered
            ],
        }
    return result


def _products_with_sizes():
    return Product.objects.filter(is_available=True).prefetch_related(
        "sizes__store"
    ).order_by("-created_at")


def _other_stores(grouped, store, stores):
    others = []
    for other in stores:
        if store is not None and other.pk == store.pk:
            continue
        sizes = sort_sizes(grouped.get(other.pk, []))
        total = _total(sizes)
        if total:
            others.append({"store": other, "sizes": sizes, "total": total})
    return others


def size_run(grouped, store):
    """Все размеры товара: сколько в выбранной точке и сколько в остальных."""
    run = {}
    for store_id, sizes in grouped.items():
        for stock in sizes:
            entry = run.setdefault(
                stock.size,
                {
                    "size": stock.size,
                    "here": 0,
                    "elsewhere": 0,
                    "stores": [],
                },
            )
            if store is not None and store_id == store.pk:
                entry["here"] += stock.quantity
            else:
                entry["elsewhere"] += stock.quantity
                if stock.quantity:
                    entry["stores"].append(store_id)
    return sorted(run.values(), key=lambda entry: _size_key(entry["size"]))


def catalog_products(store):
    """Товары, которые есть хотя бы в одной точке.

    Для каждого товара возвращаются размеры выбранной точки и наличие
    в остальных точках, чтобы карточка могла предложить другую точку.
    """
    stores = active_stores()
    items = []
    for product in _products_with_sizes():
        grouped = _sizes_by_store(product)
        total_all = sum(_total(sizes) for sizes in grouped.values())
        if total_all == 0:
            continue
        current = sort_sizes(grouped.get(store.pk, [])) if store else []
        items.append(
            {
                "product": product,
                "sizes": current,
                "size_run": size_run(grouped, store),
                "stores": stock_map(grouped),
                "total_stock": _total(current),
                "other_stores": _other_stores(grouped, store, stores),
                "total_all": total_all,
            }
        )
    return items


def product_availability(product, store):
    """Наличие конкретного товара: размеры выбранной точки и других точек."""
    product = (
        Product.objects.filter(pk=product.pk)
        .prefetch_related("sizes__store")
        .first()
    )
    if product is None:
        return None
    stores = active_stores()
    grouped = _sizes_by_store(product)
    current = sort_sizes(grouped.get(store.pk, [])) if store else []
    return {
        "product": product,
        "sizes": current,
        "size_run": size_run(grouped, store),
        "stores": stock_map(grouped),
        "total_stock": _total(current),
        "other_stores": _other_stores(grouped, store, stores),
        "total_all": sum(_total(sizes) for sizes in grouped.values()),
    }


def sold_out_products():
    """Товары, распроданные во всех точках — для отдельной страницы."""
    stores = active_stores()
    items = []
    for product in _products_with_sizes():
        grouped = _sizes_by_store(product)
        if sum(_total(sizes) for sizes in grouped.values()) > 0:
            continue
        points = [
            {"store": point, "sizes": sort_sizes(grouped.get(point.pk, []))}
            for point in stores
            if grouped.get(point.pk)
        ]
        items.append(
            {
                "product": product,
                "points": points,
                "size_count": sum(len(point["sizes"]) for point in points),
            }
        )
    return items
