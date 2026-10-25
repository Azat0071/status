import json
import secrets
from datetime import timedelta
from json import JSONDecodeError

from django.contrib import admin, messages
from django.conf import settings
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

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
    PendingPhoneRegistration,
    Product,
    ProductSize,
)
from .phone import normalize_phone
from .telegram_bot import send_bot_message, send_contact_request


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
    return render(
        request,
        "glavnaia_stranisa.html",
        {
            "products": product_data,
            "customer_profile": customer_profile,
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
        if not (
            settings.TELEGRAM_BOT_TOKEN
            and settings.TELEGRAM_BOT_USERNAME
            and settings.TELEGRAM_WEBHOOK_SECRET
        ):
            form.add_error(
                None,
                "Подтверждение пока не настроено. Администратору нужно подключить Telegram-бота.",
            )
        else:
            phone = form.cleaned_data["phone"]
            now = timezone.now()
            PendingPhoneRegistration.objects.filter(expires_at__lte=now).delete()
            existing_pending = PendingPhoneRegistration.objects.filter(
                phone=phone,
                expires_at__gt=now,
                user__isnull=True,
            ).first()
            if existing_pending:
                form.add_error(
                    "phone",
                    "Для этого номера уже ожидается подтверждение. Откройте прежнюю ссылку Telegram или попробуйте через 10 минут.",
                )
            else:
                safe_next = request.POST.get("next", "")
                if not url_has_allowed_host_and_scheme(
                    safe_next,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    safe_next = ""
                pending = PendingPhoneRegistration.objects.create(
                    phone=phone,
                    first_name=form.cleaned_data["first_name"].strip(),
                    password_hash=make_password(form.cleaned_data["password1"]),
                    expires_at=now + timedelta(minutes=10),
                    target_user=form.existing_user,
                )
                request.session["phone_registration_token"] = pending.token
                request.session["phone_registration_next"] = safe_next
                return render(
                    request,
                    "account.html",
                    {
                        "mode": "telegram_pending",
                        "title": "Подтвердите номер",
                        "telegram_url": (
                            f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}"
                            f"?start={pending.token}"
                        ),
                        "verification_status_url": reverse("phone_verification_status"),
                    },
                )
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


@require_GET
def phone_verification_status(request):
    token = request.session.get("phone_registration_token")
    if not token:
        return JsonResponse({"status": "missing"}, status=400)
    pending = PendingPhoneRegistration.objects.select_related("user").filter(
        token=token
    ).first()
    if pending is None or pending.expires_at <= timezone.now():
        request.session.pop("phone_registration_token", None)
        request.session.pop("phone_registration_next", None)
        return JsonResponse({"status": "expired"})
    if pending.user_id is None:
        return JsonResponse({"status": "pending"})

    next_url = request.session.pop("phone_registration_next", "")
    request.session.pop("phone_registration_token", None)
    login(request, pending.user, backend="django.contrib.auth.backends.ModelBackend")
    pending.delete()
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = reverse("customer_profile")
    return JsonResponse({"status": "verified", "redirect_url": next_url})


@csrf_exempt
@require_POST
def telegram_webhook(request):
    configured_secret = settings.TELEGRAM_WEBHOOK_SECRET
    received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not configured_secret or not secrets.compare_digest(
        configured_secret,
        received_secret,
    ):
        return JsonResponse({"error": "Недействительный секрет вебхука."}, status=403)

    try:
        update = json.loads(request.body)
    except (JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Некорректный JSON."}, status=400)
    if not isinstance(update, dict):
        return JsonResponse({"error": "Некорректное событие Telegram."}, status=400)

    message = update.get("message")
    if not isinstance(message, dict):
        return JsonResponse({"ok": True})
    chat = message.get("chat")
    sender = message.get("from")
    if not isinstance(chat, dict) or not isinstance(sender, dict):
        return JsonResponse({"ok": True})
    if chat.get("type") != "private" or not isinstance(sender.get("id"), int):
        return JsonResponse({"ok": True})
    chat_id = chat.get("id")
    text = message.get("text", "")
    contact = message.get("contact")

    if isinstance(text, str) and text.startswith("/start"):
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            send_bot_message(chat_id, "Откройте бота по ссылке со страницы регистрации STATUS.")
            return JsonResponse({"ok": True})
        pending = PendingPhoneRegistration.objects.filter(
            token=parts[1],
            user__isnull=True,
            expires_at__gt=timezone.now(),
        ).first()
        if pending is None:
            send_bot_message(chat_id, "Ссылка подтверждения истекла. Вернитесь на сайт и начните регистрацию заново.")
            return JsonResponse({"ok": True})
        send_contact_request(chat_id)
        return JsonResponse({"ok": True})

    if not isinstance(contact, dict):
        return JsonResponse({"ok": True})
    if contact.get("user_id") != sender["id"]:
        send_bot_message(chat_id, "Пожалуйста, используйте кнопку «Подтвердить мой номер» и отправьте свой контакт.")
        return JsonResponse({"ok": True})

    try:
        contact_phone = normalize_phone(contact.get("phone_number", ""))
    except (ValidationError, AttributeError):
        send_bot_message(chat_id, "Не удалось распознать номер. На сайте укажите номер в международном формате.")
        return JsonResponse({"ok": True})

    try:
        with transaction.atomic():
            pending = PendingPhoneRegistration.objects.select_for_update().filter(
                phone=contact_phone,
                user__isnull=True,
                expires_at__gt=timezone.now(),
            ).first()
            if pending is None:
                send_bot_message(chat_id, "Для этого номера нет ожидающей регистрации. Вернитесь на сайт и начните заново.")
                return JsonResponse({"ok": True})

            User = get_user_model()
            existing_profile = CustomerProfile.objects.select_for_update().filter(
                phone=contact_phone
            ).exclude(user=pending.target_user).first()
            existing_username = User.objects.filter(
                username=contact_phone
            ).exclude(pk=pending.target_user_id).exists()
            if existing_profile or existing_username:
                send_bot_message(chat_id, "Этот номер уже зарегистрирован. Войдите в свой аккаунт.")
                pending.delete()
                return JsonResponse({"ok": True})

            if pending.target_user_id:
                user = User.objects.select_for_update().get(pk=pending.target_user_id)
                user.username = contact_phone
                user.first_name = pending.first_name
                user.email = ""
                user.password = pending.password_hash
                user.save(update_fields=("username", "first_name", "email", "password"))
                profile = CustomerProfile.objects.select_for_update().get(user=user)
                profile.phone = contact_phone
                profile.phone_verified = True
                profile.save(update_fields=("phone", "phone_verified"))
            else:
                user = User(
                    username=contact_phone,
                    first_name=pending.first_name,
                    email="",
                    password=pending.password_hash,
                )
                user.save(force_insert=True)
                CustomerProfile.objects.create(
                    user=user,
                    phone=contact_phone,
                    phone_verified=True,
                )
            pending.user = user
            pending.password_hash = ""
            pending.save(update_fields=("user", "password_hash"))
    except IntegrityError:
        send_bot_message(chat_id, "Не удалось создать аккаунт. Проверьте номер и начните регистрацию заново.")
        return JsonResponse({"ok": True})

    send_bot_message(chat_id, "Номер подтверждён. Возвращайтесь на сайт STATUS — вы войдёте автоматически.")
    return JsonResponse({"ok": True})


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
        or not profile.phone_verified
        or not request.user.first_name.strip()
        or not profile.phone.strip()
    ):
        return JsonResponse(
            {"error": "Подтвердите номер телефона и заполните имя в профиле перед заказом."},
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
