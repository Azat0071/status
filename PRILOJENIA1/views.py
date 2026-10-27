import json
from json import JSONDecodeError

from django.contrib import admin, messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import (
    AdminProfileForm,
    CustomerLoginForm,
    CustomerProfileForm,
    CustomerRegistrationForm,
)
from .models import (
    CustomerProfile,
    Order,
    OrderItem,
    Product,
    ProductSize,
)


def _available_products():
    products = Product.objects.filter(is_available=True).prefetch_related("sizes")
    return [
        {
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
                for stock in product.sizes.all()
            ],
            "totalStock": sum(stock.quantity for stock in product.sizes.all()),
        }
        for product in products
    ]


def glavnaia_stranisa(request):
    product_data = _available_products()
    customer_profile = (
        CustomerProfile.objects.filter(user=request.user).first()
        if request.user.is_authenticated
        else None
    )
    customer_orders = (
        request.user.orders.prefetch_related("items").all()
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
    return render(request, "collection.html", {"products": _available_products()})


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
    orders = request.user.orders.prefetch_related("items").all()
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


@login_required
@require_POST
def create_order(request):
    try:
        payload = json.loads(request.body)
    except (JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Не удалось прочитать данные заказа."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Некорректные данные заказа."}, status=400)

    address = payload.get("address")
    items = payload.get("items")
    if not isinstance(address, str) or not address.strip() or len(address.strip()) > 250:
        return JsonResponse({"error": "Укажите адрес доставки."}, status=400)
    if not isinstance(items, list) or not items or len(items) > 50:
        return JsonResponse({"error": "Корзина пуста или содержит слишком много товаров."}, status=400)

    quantities = {}
    for item in items:
        if not isinstance(item, dict):
            return JsonResponse({"error": "Некорректный товар в корзине."}, status=400)
        product_id = item.get("id")
        quantity = item.get("quantity")
        if (
            isinstance(product_id, bool)
            or not isinstance(product_id, int)
            or isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity < 1
        ):
            return JsonResponse({"error": "Некорректное количество товара."}, status=400)
        if product_id in quantities:
            return JsonResponse({"error": "Один товар указан в заказе несколько раз."}, status=400)
        quantities[product_id] = quantity

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

    try:
        with transaction.atomic():
            products = {
                product.pk: product
                for product in Product.objects.select_for_update()
                .filter(pk__in=quantities, is_available=True)
                .order_by("pk")
            }
            if len(products) != len(quantities):
                return JsonResponse(
                    {"error": "Некоторые товары больше недоступны. Обновите страницу."},
                    status=400,
                )

            stock_by_product = {}
            for product_id, product in products.items():
                stock_by_product[product_id] = list(
                    ProductSize.objects.select_for_update()
                    .filter(product=product)
                    .order_by("size")
                )
                available = sum(size.quantity for size in stock_by_product[product_id])
                if quantities[product_id] > available:
                    return JsonResponse(
                        {"error": f"Недостаточно товара «{product.name}» в наличии."},
                        status=400,
                    )

            full_name = request.user.get_full_name().strip() or request.user.first_name.strip()
            total_price = sum(
                products[product_id].price * quantity
                for product_id, quantity in quantities.items()
            )
            order = Order.objects.create(
                user=request.user,
                customer_name=full_name,
                customer_phone=profile.phone,
                delivery_address=address.strip(),
                total_price=total_price,
            )

            for product_id, quantity in quantities.items():
                product = products[product_id]
                remaining = quantity
                allocations = []
                for stock in stock_by_product[product_id]:
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
                    quantity=quantity,
                    sizes=", ".join(allocations),
                    unit_price=product.price,
                )
    except (Product.DoesNotExist, ProductSize.DoesNotExist):
        return JsonResponse(
            {"error": "Не удалось проверить остатки. Обновите страницу и попробуйте снова."},
            status=409,
        )

    return JsonResponse(
        {"success": True, "order_id": order.pk, "message": f"Заказ №{order.pk} оформлен."},
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
