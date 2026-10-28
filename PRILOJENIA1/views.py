import json
import uuid
from collections import defaultdict
from json import JSONDecodeError

from django.contrib import admin, messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .availability import (
    catalog_products,
    product_availability,
    sold_out_products,
    sort_sizes,
)
from .forms import (
    AdminProfileForm,
    CustomerLoginForm,
    CustomerProfileForm,
    CustomerRegistrationForm,
)
from .checkout import attach_checkout_groups
from .middleware import select_store as remember_store
from .models import (
    CustomerProfile,
    Order,
    OrderItem,
    Product,
    ProductSize,
    RestockRequest,
    Store,
)


def _active_store(raw_id):
    """Активная точка по id из POST; некорректное значение не роняет запрос."""
    try:
        store_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    return Store.objects.filter(pk=store_id, is_active=True).first()




def _product_payload(item):
    product = item["product"]
    return {
        "id": product.id,
        "name": product.name,
        "category": product.category,
        "categoryLabel": product.get_category_display(),
        "priceKGS": product.price,
        "desc": product.description,
        "image": product.image.url,
        "color": product.color,
        "material": product.material,
        "sizes": [
            {"size": stock.size, "quantity": stock.quantity}
            for stock in item["sizes"]
        ],
        "totalStock": item["total_stock"],
        "storeStock": item["stores"],
        "otherStores": [
            {
                "id": other["store"].id,
                "name": other["store"].name,
                "address": other["store"].address,
                "total": other["total"],
            }
            for other in item["other_stores"]
        ],
    }


def _catalog_payload(store):
    return [_product_payload(item) for item in catalog_products(store)]


def glavnaia_stranisa(request):
    product_data = _catalog_payload(request.store)
    customer_profile = (
        CustomerProfile.objects.filter(user=request.user).first()
        if request.user.is_authenticated
        else None
    )
    customer_orders = (
        attach_checkout_groups(
            request.user.orders.prefetch_related("items").select_related("store").all()
        )
        if request.user.is_authenticated
        else ()
    )
    return render(
        request,
        "glavnaia_stranisa.html",
        {
            "products": product_data,
            "customer_profile": customer_profile,
            "customer_orders": customer_orders,
            "customer_name": (
                request.user.get_full_name() or request.user.username
                if request.user.is_authenticated
                else "Войдите, чтобы оформить заказ"
            ),
        },
    )


def collection(request):
    return render(
        request,
        "collection.html",
        {
            "catalog": catalog_products(request.store),
            "product_count": Product.objects.filter(is_available=True).count(),
        },
    )


def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk, is_available=True)
    availability = product_availability(product, request.store)
    return render(
        request,
        "product.html",
        {
            "product": product,
            "availability": availability,
        },
    )


MAX_CART_ITEMS = 50


def _cart_lines(payload, default_store):
    """Разбирает строки корзины. Возвращает (строки, текст ошибки)."""
    items = payload.get("items")
    if not isinstance(items, list) or not items or len(items) > MAX_CART_ITEMS:
        return None, "Корзина пуста или содержит слишком много товаров."

    lines = {}
    for item in items:
        if not isinstance(item, dict):
            return None, "Некорректный товар в корзине."
        product_id = item.get("id")
        quantity = item.get("quantity")
        if (
            isinstance(product_id, bool)
            or not isinstance(product_id, int)
            or isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity < 1
        ):
            return None, "Некорректное количество товара."
        raw_store = item.get("store")
        if raw_store is None:
            raw_store = default_store.pk if default_store else 0
        try:
            store_id = int(raw_store)
        except (TypeError, ValueError):
            return None, "Некорректная точка самовывоза."
        key = (product_id, store_id)
        if key in lines:
            return None, "Один товар указан в заказе несколько раз."
        lines[key] = quantity
    return lines, None


def _availability_report(lines, *, lock=False):
    """Сверяет корзину с остатками: что доступно, что короче, что ушло."""
    product_ids = {product_id for product_id, _ in lines}

    products_query = Product.objects.filter(pk__in=product_ids, is_available=True)
    stocks_query = ProductSize.objects.filter(product__in=product_ids)
    if lock:
        products_query = products_query.select_for_update().order_by("pk")
        stocks_query = stocks_query.select_for_update().order_by("pk")

    products = {product.pk: product for product in products_query}
    stocks = list(stocks_query.select_related("store"))

    by_pair = defaultdict(list)
    totals = defaultdict(lambda: defaultdict(int))
    for stock in stocks:
        by_pair[(stock.product_id, stock.store_id)].append(stock)
        totals[stock.product_id][stock.store_id] += stock.quantity

    active_stores = {store.pk: store for store in Store.objects.filter(is_active=True)}

    report = []
    for (product_id, store_id), requested in lines.items():
        product = products.get(product_id)
        store = active_stores.get(store_id)
        available = totals[product_id].get(store_id, 0) if product and store else 0
        if product is None or store is None or available == 0:
            status = "gone"
        elif available < requested:
            status = "short"
        else:
            status = "ok"

        report.append(
            {
                "product_id": product_id,
                "product_name": product.name if product else "Товар недоступен",
                "price": product.price if product else 0,
                "image": product.image.url if product else "",
                "sku": (product.sku or "") if product else "",
                "store_id": store_id,
                "store_name": store.name if store else "Точка закрыта",
                "requested": requested,
                "available": available,
                "status": status,
                "others": [
                    {
                        "store_id": other_id,
                        "store_name": active_stores[other_id].name,
                        "total": quantity,
                    }
                    for other_id, quantity in totals[product_id].items()
                    if other_id != store_id
                    and quantity > 0
                    and other_id in active_stores
                ],
            }
        )
    return report, products, by_pair


@require_POST
def validate_cart(request):
    """Предпросмотр корзины: сколько реально можно забрать из выбранных точек."""
    try:
        payload = json.loads(request.body)
    except (JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Не удалось прочитать корзину."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Некорректные данные корзины."}, status=400)

    lines, error = _cart_lines(payload, request.store or Store.default())
    if error:
        return JsonResponse({"error": error}, status=400)

    report, _, _ = _availability_report(lines)
    return JsonResponse({"lines": report})


def out_of_stock(request):
    if request.method == "POST":
        return _create_restock_request(request)

    items = sold_out_products()
    category_counts = {}
    for item in items:
        code = item["product"].category
        category_counts[code] = category_counts.get(code, 0) + 1
    categories = [
        {"code": code, "label": label, "count": category_counts.get(code, 0)}
        for code, label in Product.Category.choices
    ]
    profile = (
        CustomerProfile.objects.filter(user=request.user).first()
        if request.user.is_authenticated
        else None
    )
    return render(
        request,
        "out_of_stock.html",
        {
            "items": items,
            "item_count": len(items),
            "size_count": sum(item["size_count"] for item in items),
            "categories": categories,
            "contact_phone": profile.phone if profile else "",
            "kinds": RestockRequest.Kind.choices,
        },
    )


def _create_restock_request(request):
    product = get_object_or_404(
        Product, pk=request.POST.get("product"), is_available=True
    )
    kind = request.POST.get("kind")
    if kind not in RestockRequest.Kind.values:
        kind = RestockRequest.Kind.NOTIFY
    phone = (request.POST.get("phone") or "").strip()
    comment = (request.POST.get("comment") or "").strip()[:500]
    size = (request.POST.get("size") or "").strip()[:20]

    if not phone:
        messages.error(request, "Укажите телефон, чтобы ателье могло ответить.")
        return redirect("out_of_stock")

    RestockRequest.objects.create(
        product=product,
        size=size,
        kind=kind,
        phone=phone,
        comment=comment,
        store=request.store,
        user=request.user if request.user.is_authenticated else None,
    )
    messages.success(
        request,
        f"Запрос по «{product.name}» принят. Ателье ответит на {phone}.",
    )
    return redirect("out_of_stock")


@require_POST
def select_store(request):
    store = _active_store(request.POST.get("store"))
    if store is not None:
        remember_store(request, store)

    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = ""
    return redirect(next_url or request.META.get("HTTP_REFERER") or reverse("home"))


class CustomerLoginView(LoginView):
    template_name = "account.html"
    authentication_form = CustomerLoginForm
    extra_context = {"mode": "login", "title": "Вход в STATUS"}


def customer_register(request):
    if request.user.is_authenticated:
        return redirect("customer_profile")
    form = CustomerRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        safe_next = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(
            safe_next,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            safe_next = ""
        phone = form.cleaned_data["phone"]
        try:
            with transaction.atomic():
                user = get_user_model().objects.create_user(
                    username=phone,
                    first_name=form.cleaned_data["first_name"].strip(),
                    email="",
                    password=form.cleaned_data["password1"],
                )
                CustomerProfile.objects.create(user=user, phone=phone)
        except IntegrityError:
            form.add_error("phone", "Этот номер уже зарегистрирован. Войдите в аккаунт.")
        else:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect(safe_next or reverse("customer_profile"))
    return render(
        request,
        "account.html",
        {
            "form": form,
            "mode": "register",
            "title": "Регистрация в STATUS",
            "next": request.POST.get("next", request.GET.get("next", "")),
        },
    )


@login_required
def customer_profile(request):
    form = CustomerProfileForm(
        request.POST or None,
        user=request.user,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Профиль сохранён.")
        return redirect("customer_profile")
    orders = attach_checkout_groups(
        request.user.orders.prefetch_related("items").select_related("store").all()
    )
    return render(
        request,
        "account.html",
        {
            "form": form,
            "mode": "profile",
            "title": "Мой профиль",
            "orders": orders,
            "customer_profile": CustomerProfile.objects.filter(
                user=request.user
            ).first(),
        },
    )


@require_POST
def customer_logout(request):
    logout(request)
    return redirect("home")


def _orders_payload(orders):
    return [
        {
            "id": order.pk,
            "store": order.store.name if order.store else "",
            "store_id": order.store_id,
            "total": order.total_price,
            "items": order.items.count(),
        }
        for order in orders
    ]


@login_required
@require_POST
def create_order(request):
    """Оформляет корзину: по заказу на каждую точку, конфликты — до записи."""
    try:
        payload = json.loads(request.body)
    except (JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Не удалось прочитать данные заказа."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Некорректные данные заказа."}, status=400)

    address = payload.get("address")
    if not isinstance(address, str) or not address.strip() or len(address.strip()) > 250:
        return JsonResponse({"error": "Укажите адрес доставки."}, status=400)

    default_store = request.store or Store.default()
    lines, error = _cart_lines(payload, default_store)
    if error:
        return JsonResponse({"error": error}, status=400)

    checkout_id = None
    raw_checkout_id = payload.get("checkout_id")
    if raw_checkout_id:
        try:
            checkout_id = uuid.UUID(str(raw_checkout_id))
        except (TypeError, ValueError, AttributeError):
            return JsonResponse({"error": "Некорректная группа оформления."}, status=400)

    if checkout_id is not None:
        existing = list(
            Order.objects.filter(checkout_id=checkout_id).select_related("store")
        )
        if existing:
            return JsonResponse(
                {
                    "success": True,
                    "duplicate": True,
                    "orders": _orders_payload(existing),
                    "dropped": [],
                    "checkout_id": str(checkout_id),
                }
            )

    profile = CustomerProfile.objects.filter(user=request.user).first()
    if (
        profile is None
        or not request.user.first_name.strip()
        or not profile.phone.strip()
    ):
        return JsonResponse(
            {"error": "Заполните имя и телефон в профиле перед заказом."},
            status=400,
        )

    confirm_partial = bool(payload.get("confirm_partial"))
    full_name = request.user.get_full_name().strip() or request.user.first_name.strip()
    batch_id = checkout_id or uuid.uuid4()

    with transaction.atomic():
        report, products, by_pair = _availability_report(lines, lock=True)
        conflicts = [line for line in report if line["status"] != "ok"]
        available_lines = [line for line in report if line["status"] == "ok"]

        if conflicts and not confirm_partial:
            return JsonResponse(
                {
                    "error": "Часть позиций больше недоступна.",
                    "conflicts": conflicts,
                    "created": [],
                },
                status=409,
            )
        if not available_lines:
            return JsonResponse(
                {
                    "error": "Все позиции корзины недоступны.",
                    "conflicts": conflicts,
                    "created": [],
                },
                status=409,
            )

        grouped = defaultdict(list)
        for line in available_lines:
            grouped[line["store_id"]].append(line)

        orders = []
        for store_id in sorted(grouped):
            store = Store.objects.get(pk=store_id)
            group = grouped[store_id]
            total_price = sum(
                products[line["product_id"]].price * line["requested"]
                for line in group
            )
            order = Order.objects.create(
                user=request.user,
                customer_name=full_name,
                customer_phone=profile.phone,
                delivery_address=address.strip(),
                total_price=total_price,
                store=store,
                checkout_id=batch_id,
            )
            for line in group:
                product = products[line["product_id"]]
                remaining = line["requested"]
                allocations = []
                for stock in sort_sizes(by_pair[(product.pk, store_id)]):
                    taken = min(stock.quantity, remaining)
                    if taken:
                        stock.quantity -= taken
                        stock.save(update_fields=("quantity",))
                        allocations.append(f"{stock.size} × {taken}")
                        remaining -= taken
                    if not remaining:
                        break
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    product_name=product.name,
                    quantity=line["requested"],
                    sizes=", ".join(allocations),
                    unit_price=product.price,
                )
            orders.append(order)

    return JsonResponse(
        {
            "success": True,
            "orders": _orders_payload(orders),
            "dropped": conflicts,
            "checkout_id": str(batch_id),
            "message": f"Оформлено заказов: {len(orders)}.",
        },
        status=201,
    )


def admin_profile(request):
    profile_form = AdminProfileForm(instance=request.user)
    password_form = PasswordChangeForm(request.user)
    password_form.fields["old_password"].label = "Текущий пароль"
    password_form.fields["new_password1"].label = "Новый пароль"
    password_form.fields["new_password2"].label = "Повторите новый пароль"

    if request.method == "POST":
        if request.POST.get("action") == "password":
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Пароль успешно изменён.")
                return redirect("admin_profile")
        else:
            profile_form = AdminProfileForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Данные профиля сохранены.")
                return redirect("admin_profile")

    context = {
        **admin.site.each_context(request),
        "title": "Профиль администратора",
        "profile_form": profile_form,
        "password_form": password_form,
    }
    return render(request, "admin/profile.html", context)
