from django.contrib import admin, messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import redirect, render

from .forms import AdminProfileForm
from .models import Product, ProductSize


def glavnaia_stranisa(request):
    products = Product.objects.filter(is_available=True).prefetch_related("sizes")
    product_data = [
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
    return render(request, "glavnaia_stranisa.html", {"products": product_data})


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
