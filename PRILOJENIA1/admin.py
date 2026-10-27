from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.sessions.models import Session
from django.db.models import BooleanField, Case, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline

from .models import Order, OrderItem, Product, ProductSize


class ProductSizeInline(TabularInline):
    model = ProductSize
    extra = 2
    fields = ("size", "quantity")
    verbose_name = "Размер и остаток"
    verbose_name_plural = "Остатки на складе по размерам"


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = (
        "name",
        "category",
        "price",
        "total_stock",
        "is_available",
        "created_at",
    )
    list_filter = ("category", "is_available")
    search_fields = ("name", "description", "material", "color")
    list_editable = ("is_available",)
    list_per_page = 25
    inlines = (ProductSizeInline,)
    fieldsets = (
        ("Основная информация", {
            "fields": ("name", "category", "description"),
        }),
        ("Цена и фотографии", {
            "fields": ("price", "image"),
        }),
        ("Характеристики (необязательно)", {
            "fields": ("color", "material"),
        }),
        ("Публикация", {
            "fields": ("is_available", "created_at"),
        }),
    )
    readonly_fields = ("created_at",)

    @admin.display(description="Всего на складе", ordering="stock_total")
    def total_stock(self, obj):
        return obj.stock_total

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            stock_total=Coalesce(Sum("sizes__quantity"), 0)
        )


def _active_sessions_by_user():
    sessions_by_user = {}
    active_sessions = Session.objects.filter(expire_date__gt=timezone.now())
    for session in active_sessions.iterator():
        user_id = session.get_decoded().get(SESSION_KEY)
        if user_id is not None:
            sessions_by_user.setdefault(str(user_id), []).append(session.pk)
    return sessions_by_user


def _invalidate_user_sessions(user_ids):
    sessions_by_user = _active_sessions_by_user()
    sessions_to_delete = [
        session_id
        for user_id in user_ids
        for session_id in sessions_by_user.get(str(user_id), [])
    ]
    if sessions_to_delete:
        Session.objects.filter(pk__in=sessions_to_delete).delete()


class StatusUserAdmin(UserAdmin):
    list_display = (
        "username",
        "first_name",
        "phone_number",
        "email",
        "is_online",
        "is_active",
        "last_login",
        "date_joined",
    )
    list_filter = ("is_active", "is_staff", "date_joined")
    search_fields = ("username", "first_name", "last_name", "email")
    actions = ("delete_selected", "block_users", "unblock_users")
    ordering = ("-date_joined",)

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("customer_profile")
        online_user_ids = _active_sessions_by_user()
        return queryset.annotate(
            online_status=Case(
                When(pk__in=online_user_ids.keys(), then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )

    @admin.display(boolean=True, description="В сети")
    def is_online(self, user):
        return user.online_status

    @admin.display(description="Телефон")
    def phone_number(self, user):
        profile = getattr(user, "customer_profile", None)
        return profile.phone if profile else "—"

    @admin.action(description="Заблокировать выбранных пользователей")
    def block_users(self, request, queryset):
        protected = queryset.filter(is_superuser=True).count()
        users_to_block = queryset.exclude(is_superuser=True).exclude(pk=request.user.pk)
        user_ids = list(users_to_block.values_list("pk", flat=True))
        blocked_count = users_to_block.update(is_active=False)
        _invalidate_user_sessions(user_ids)
        if blocked_count:
            self.message_user(
                request,
                f"Заблокировано пользователей: {blocked_count}. Их активные сеансы завершены.",
                messages.SUCCESS,
            )
        if protected:
            self.message_user(
                request,
                "Суперпользователей нельзя заблокировать этим действием.",
                messages.WARNING,
            )
        if not blocked_count and not protected:
            self.message_user(request, "Нет пользователей для блокировки.", messages.WARNING)

    @admin.action(description="Разблокировать выбранных пользователей")
    def unblock_users(self, request, queryset):
        updated_count = queryset.update(is_active=True)
        self.message_user(
            request,
            f"Разблокировано пользователей: {updated_count}.",
            messages.SUCCESS,
        )


User = get_user_model()
admin.site.unregister(User)
admin.site.register(User, StatusUserAdmin)


class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ("product_name", "quantity", "sizes", "unit_price")
    readonly_fields = fields


@admin.register(Order, site=admin.site)
class OrderAdmin(ModelAdmin):
    list_display = (
        "id",
        "customer_name",
        "customer_phone",
        "total_price",
        "status",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("customer_name", "customer_phone", "user__email")
    list_editable = ("status",)
    readonly_fields = (
        "user",
        "customer_name",
        "customer_phone",
        "delivery_address",
        "total_price",
        "created_at",
    )
    fields = readonly_fields + ("status",)
    inlines = (OrderItemInline,)
