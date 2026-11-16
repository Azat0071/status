from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.sessions.models import Session
from django.db.models import (
    BooleanField,
    Case,
    Count,
    IntegerField,
    OuterRef,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    CustomerProfile,
    Order,
    OrderItem,
    Product,
    ProductImage,
    ProductSize,
    RestockRequest,
    SiteContactSettings,
    StockMovement,
    Store,
)

LOW_STOCK_LIMIT = 3


@admin.register(SiteContactSettings)
class SiteContactSettingsAdmin(ModelAdmin):
    fieldsets = (
        ("Контакты", {"fields": ("phone", "email")}),
        ("Социальные сети", {"fields": ("whatsapp_url",)}),
    )

    def has_add_permission(self, request):
        return not SiteContactSettings.objects.filter(pk=1).exists()

    def has_delete_permission(self, request, obj=None):
        return False


def _parse_sizes(sizes_field):
    """'M × 2, L × 1' → [('M', 2), ('L', 1)]."""
    result = []
    for chunk in (sizes_field or "").split(","):
        if "×" not in chunk:
            continue
        name, _, count = chunk.partition("×")
        name = name.strip()
        try:
            result.append((name, int(count.strip())))
        except ValueError:
            continue
    return result


class ProductSizeInline(TabularInline):
    model = ProductSize
    extra = 2
    can_delete = False
    fields = ("store", "size", "quantity", "stock_hint")
    readonly_fields = ("stock_hint",)
    verbose_name = "Размер и остаток"
    verbose_name_plural = "Остатки по размерам и точкам"

    @admin.display(description="Продано всего")
    def stock_hint(self, obj):
        if obj and obj.pk:
            sold = (
                obj.movements.filter(kind=StockMovement.Kind.SALE).aggregate(
                    total=Sum("quantity")
                )["total"]
                or 0
            )
            return f"−{abs(sold)}"
        return "—"


class ProductImageInline(TabularInline):
    model = ProductImage
    extra = 2
    fields = ("image", "position")
    verbose_name = "Дополнительное фото"
    verbose_name_plural = "Дополнительные фотографии"


class ProductSizeLowStockFilter(admin.SimpleListFilter):
    title = "остаток"
    parameter_name = "stock_level"

    def lookups(self, request, model_admin):
        return (
            ("low", "Мало (≤ %d)" % LOW_STOCK_LIMIT),
            ("out", "Нет в наличии"),
            ("ok", "В наличии"),
        )

    def queryset(self, request, queryset):
        if self.value() == "low":
            return queryset.filter(quantity__gt=0, quantity__lte=LOW_STOCK_LIMIT)
        if self.value() == "out":
            return queryset.filter(quantity=0)
        if self.value() == "ok":
            return queryset.filter(quantity__gt=LOW_STOCK_LIMIT)
        return queryset


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = (
        "image_preview",
        "name",
        "category",
        "price",
        "total_stock",
        "sold_count",
        "is_available",
        "created_at",
    )
    list_display_links = ("image_preview", "name")
    list_filter = ("category", "is_available")
    search_fields = ("name", "sku", "description", "material", "color")
    list_editable = ("is_available",)
    list_per_page = 25
    inlines = (ProductSizeInline, ProductImageInline)
    actions = ("publish_products", "unpublish_products", "duplicate_products")
    fieldsets = (
        ("Основная информация", {
            "fields": ("name", "category", "description"),
        }),
        ("Цена и фотографии", {
            "fields": ("price", "image"),
        }),
        ("Характеристики (необязательно)", {
            "fields": ("color", "material", "search_keywords"),
        }),
        ("Публикация", {
            "fields": ("is_available", "created_at"),
        }),
    )
    readonly_fields = ("created_at",)

    @admin.display(description="Всего на складе", ordering="stock_total")
    def total_stock(self, obj):
        return obj.stock_total

    @admin.display(description="Продано", ordering="sold_total")
    def sold_count(self, obj):
        return obj.sold_total

    @admin.display(description="")
    def image_preview(self, obj):
        from django.utils.html import format_html

        if obj.image:
            return format_html(
                '<img src="{}" style="width:44px;height:44px;object-fit:cover;border-radius:4px;" />',
                obj.image.url,
            )
        return "—"

    def get_queryset(self, request):
        stock_total = (
            ProductSize.objects.filter(product_id=OuterRef("pk"))
            .order_by()
            .values("product_id")
            .annotate(total=Sum("quantity"))
            .values("total")[:1]
        )
        sold_total = (
            OrderItem.objects.filter(product_id=OuterRef("pk"))
            .order_by()
            .values("product_id")
            .annotate(total=Sum("quantity"))
            .values("total")[:1]
        )
        return (
            super()
            .get_queryset(request)
            .annotate(
                stock_total=Coalesce(
                    Subquery(stock_total, output_field=IntegerField()), Value(0)
                ),
                sold_total=Coalesce(
                    Subquery(sold_total, output_field=IntegerField()), Value(0)
                ),
            )
        )

    def save_formset(self, request, form, formset, change):
        if formset.model is not ProductSize:
            return super().save_formset(request, form, formset, change)

        previous_quantities = {
            stock.pk: stock.quantity for stock in formset.get_queryset()
        }
        instances = formset.save(commit=False)
        for stock in formset.deleted_objects:
            stock.delete()
        for stock in instances:
            previous_quantity = previous_quantities.get(stock.pk)
            stock.save()
            quantity_change = stock.quantity - (previous_quantity or 0)
            if quantity_change:
                is_new_stock = previous_quantity is None
                StockMovement.objects.create(
                    stock=stock,
                    kind=(
                        StockMovement.Kind.RESTOCK
                        if is_new_stock and quantity_change > 0
                        else StockMovement.Kind.ADJUST
                    ),
                    quantity=quantity_change,
                    comment=(
                        "Приход через карточку товара"
                        if is_new_stock
                        else "Изменение через карточку товара"
                    ),
                    created_by=request.user,
                )
        formset.save_m2m()

    @admin.action(description="Опубликовать на сайте")
    def publish_products(self, request, queryset):
        updated = queryset.update(is_available=True)
        self.message_user(request, f"Опубликовано товаров: {updated}.", messages.SUCCESS)

    @admin.action(description="Снять с публикации")
    def unpublish_products(self, request, queryset):
        updated = queryset.update(is_available=False)
        self.message_user(request, f"Снято с публикации: {updated}.", messages.SUCCESS)

    @admin.action(description="Дублировать товар (без остатков)")
    def duplicate_products(self, request, queryset):
        created = 0
        for product in queryset:
            product.pk = None
            product.sku = None
            product.name = f"{product.name} (копия)"
            product.save()
            created += 1
        self.message_user(request, f"Создано копий: {created}.", messages.SUCCESS)


@admin.register(ProductSize)
class ProductSizeAdmin(ModelAdmin):
    """Склад: быстрый приход, корректировка и фильтры по остаткам."""

    list_display = (
        "product_link",
        "store",
        "size",
        "quantity",
        "stock_badge",
    )
    list_filter = ("store", ProductSizeLowStockFilter)
    search_fields = ("product__name", "product__sku", "size", "store__name")
    list_per_page = 50
    actions = ("add_five", "add_ten", "set_zero")

    @admin.display(description="Товар", ordering="product__name")
    def product_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html

        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:PRILOJENIA1_product_change", args=[obj.product_id]),
            obj.product.name,
        )

    @admin.display(description="Состояние")
    def stock_badge(self, obj):
        if obj.quantity == 0:
            return "нет в наличии"
        if obj.quantity <= LOW_STOCK_LIMIT:
            return f"мало: {obj.quantity}"
        return "в наличии"

    def save_model(self, request, obj, form, change):
        """Ручное изменение количества фиксируется как корректировка."""
        before = None
        if change:
            before = ProductSize.objects.filter(pk=obj.pk).values_list(
                "quantity", flat=True
            ).first()
        super().save_model(request, obj, form, change)
        if change and before is not None and before != obj.quantity:
            StockMovement.objects.create(
                stock=obj,
                kind=StockMovement.Kind.ADJUST,
                quantity=obj.quantity - before,
                comment="Изменение в админке",
                created_by=request.user,
            )

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="＋ Приход 5 шт.")
    def add_five(self, request, queryset):
        self._restock(request, queryset, 5)

    @admin.action(description="＋ Приход 10 шт.")
    def add_ten(self, request, queryset):
        self._restock(request, queryset, 10)

    @admin.action(description="Обнулить остатки")
    def set_zero(self, request, queryset):
        done = 0
        for stock in queryset.exclude(quantity=0):
            StockMovement.apply(
                stock=stock,
                kind=StockMovement.Kind.ADJUST,
                quantity=-stock.quantity,
                comment="Обнуление через действие",
                user=request.user,
            )
            done += 1
        self.message_user(request, f"Обнулено позиций: {done}.", messages.SUCCESS)

    def _restock(self, request, queryset, amount):
        for stock in queryset:
            StockMovement.apply(
                stock=stock,
                kind=StockMovement.Kind.RESTOCK,
                quantity=amount,
                comment="Быстрый приход",
                user=request.user,
            )
        self.message_user(
            request, f"Приход по позициям: +{amount} шт.", messages.SUCCESS
        )


@admin.register(StockMovement)
class StockMovementAdmin(ModelAdmin):
    """Журнал: что, когда и почему менялось на складе."""

    list_display = ("created_at", "product_name", "store_name", "size", "kind", "quantity", "comment")
    list_filter = ("kind", "stock__store", "created_at")
    search_fields = ("stock__product__name", "stock__product__sku", "comment")
    date_hierarchy = "created_at"
    list_per_page = 50

    @admin.display(description="Товар", ordering="stock__product__name")
    def product_name(self, obj):
        return obj.stock.product.name

    @admin.display(description="Точка", ordering="stock__store__name")
    def store_name(self, obj):
        return obj.stock.store.name

    @admin.display(description="Размер", ordering="stock__size")
    def size(self, obj):
        return obj.stock.size

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Store)
class StoreAdmin(ModelAdmin):
    list_display = (
        "name",
        "address",
        "city",
        "phone",
        "is_default",
        "is_active",
        "positions_count",
    )
    list_editable = ("is_active",)
    list_filter = ("city", "is_active", "is_default")
    search_fields = ("name", "address", "city", "phone", "instagram_url")

    @admin.display(description="Позиций на складе", ordering="positions")
    def positions_count(self, obj):
        return obj.positions

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            positions=Coalesce(Sum("sizes__quantity"), 0)
        )


@admin.register(CustomerProfile)
class CustomerProfileAdmin(ModelAdmin):
    list_display = ("user", "phone", "orders_count", "orders_total")
    search_fields = ("phone", "user__username", "user__first_name", "user__last_name")
    raw_id_fields = ("user",)

    @admin.display(description="Заказов")
    def orders_count(self, obj):
        return obj.orders_total_count

    @admin.display(description="Сумма, сом")
    def orders_total(self, obj):
        return obj.orders_total_sum

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                orders_total_count=Count("user__orders", distinct=True),
                orders_total_sum=Coalesce(Sum("user__orders__total_price"), 0),
            )
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
        "store",
        "checkout_id",
        "total_price",
        "status",
        "created_at",
    )
    list_filter = ("status", "store", "created_at")
    search_fields = ("customer_name", "customer_phone", "user__username", "user__email")
    date_hierarchy = "created_at"
    actions = ("mark_processing", "mark_completed", "mark_cancelled")
    readonly_fields = (
        "user",
        "customer_name",
        "customer_phone",
        "delivery_address",
        "store",
        "checkout_id",
        "total_price",
        "created_at",
        "status",
    )
    fields = readonly_fields
    inlines = (OrderItemInline,)

    @admin.action(description="Перевести в «В обработке»")
    def mark_processing(self, request, queryset):
        updated = queryset.exclude(status=Order.Status.PROCESSING).update(
            status=Order.Status.PROCESSING
        )
        self.message_user(request, f"Заказов переведено в обработку: {updated}.", messages.SUCCESS)

    @admin.action(description="Отметить как выполненные")
    def mark_completed(self, request, queryset):
        updated = queryset.exclude(status=Order.Status.COMPLETED).update(
            status=Order.Status.COMPLETED
        )
        self.message_user(request, f"Заказов выполнено: {updated}.", messages.SUCCESS)

    @admin.action(description="Отменить и вернуть товар на склад")
    def mark_cancelled(self, request, queryset):
        restored = 0
        orders = list(queryset.exclude(status=Order.Status.CANCELLED))
        for order in orders:
            for item in order.items.select_related("product"):
                if not item.product:
                    continue
                for size, taken in _parse_sizes(item.sizes):
                    stock = ProductSize.objects.filter(
                        product=item.product, store=order.store, size=size
                    ).first()
                    if stock is None:
                        continue
                    StockMovement.apply(
                        stock=stock,
                        kind=StockMovement.Kind.RETURN,
                        quantity=taken,
                        comment=f"Отмена заказа №{order.pk}",
                        order=order,
                        user=request.user,
                    )
                    restored += taken
        updated = Order.objects.filter(
            pk__in=[order.pk for order in orders]
        ).update(status=Order.Status.CANCELLED)
        self.message_user(
            request,
            f"Заказов отменено: {updated}. Возвращено на склад: {restored} шт.",
            messages.SUCCESS,
        )


@admin.register(RestockRequest)
class RestockRequestAdmin(ModelAdmin):
    list_display = (
        "product",
        "size",
        "kind",
        "phone",
        "store",
        "created_at",
    )
    list_filter = ("kind", "store", "created_at")
    search_fields = ("product__name", "phone", "comment")
    readonly_fields = ("created_at",)
    fields = ("product", "size", "kind", "phone", "comment", "store", "user", "created_at")
