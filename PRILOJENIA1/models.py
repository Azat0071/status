import uuid

from django.conf import settings
from django.db import models


def generate_phone_verification_token():
    return uuid.uuid4().hex


class Store(models.Model):
    name = models.CharField("Название", max_length=80)
    address = models.CharField("Адрес", max_length=200)
    city = models.CharField("Город", max_length=80, default="Бишкек")
    phone = models.CharField("Телефон", max_length=30, blank=True)
    working_hours = models.CharField(
        "Часы работы",
        max_length=60,
        blank=True,
        default="11:00–21:00",
    )
    is_default = models.BooleanField("Точка по умолчанию", default=False)
    is_active = models.BooleanField("Работает", default=True)

    class Meta:
        ordering = ("-is_default", "pk")
        verbose_name = "точка продаж"
        verbose_name_plural = "точки продаж"

    def __str__(self):
        return f"{self.name} — {self.address}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            Store.objects.exclude(pk=self.pk).update(is_default=False)

    @classmethod
    def default(cls):
        active = cls.objects.filter(is_active=True)
        return active.filter(is_default=True).first() or active.first()


class Product(models.Model):
    class Category(models.TextChoices):
        KNIT = "knit", "Поло и трикотаж"
        PANTS = "pants", "Брюки"
        OUTER = "outer", "Верхняя одежда"
        SHOES = "shoes", "Обувь"
        ACCESSORIES = "acc", "Аксессуары"

    name = models.CharField("Название", max_length=200)
    sku = models.CharField("Артикул", max_length=50, blank=True, null=True, unique=True)
    category = models.CharField("Категория", max_length=20, choices=Category.choices)
    price = models.PositiveIntegerField("Цена, сом")
    description = models.TextField("Описание")
    image = models.ImageField("Фотография", upload_to="products/")
    color = models.CharField("Цвет", max_length=80, blank=True)
    material = models.CharField("Материал", max_length=120, blank=True)
    is_available = models.BooleanField("Показывать на сайте", default=True)
    created_at = models.DateTimeField("Добавлен", auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "товар"
        verbose_name_plural = "товары"

    def __str__(self):
        return self.name

    @property
    def price_label(self):
        """Цена с разделителем разрядов: 21 800."""
        return f"{self.price:,}".replace(",", " ")


class ProductSize(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="sizes",
        verbose_name="Товар",
    )
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name="sizes",
        verbose_name="Точка",
    )
    size = models.CharField("Размер", max_length=20)
    quantity = models.PositiveIntegerField("Количество на складе", default=0)

    class Meta:
        ordering = ("size",)
        constraints = [
            models.UniqueConstraint(
                fields=("product", "store", "size"),
                name="unique_product_store_size",
            ),
        ]
        verbose_name = "остаток по размеру"
        verbose_name_plural = "остатки по размерам"

    def __str__(self):
        return f"{self.store.name} · {self.size}: {self.quantity}"


class CustomerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_profile",
        verbose_name="Пользователь",
    )
    phone = models.CharField("Телефон", max_length=30)

    class Meta:
        verbose_name = "профиль покупателя"
        verbose_name_plural = "профили покупателей"

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} — {self.phone}"


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новый"
        PROCESSING = "processing", "В обработке"
        COMPLETED = "completed", "Выполнен"
        CANCELLED = "cancelled", "Отменён"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name="Покупатель",
    )
    customer_name = models.CharField("Имя покупателя", max_length=150)
    customer_phone = models.CharField("Телефон", max_length=30)
    delivery_address = models.CharField("Адрес доставки", max_length=250)
    total_price = models.PositiveIntegerField("Сумма заказа")
    store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name="Точка самовывоза",
    )
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )
    checkout_id = models.UUIDField(
        "Группа оформления",
        null=True,
        blank=True,
        db_index=True,
    )
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "заказ"
        verbose_name_plural = "заказы"

    def __str__(self):
        return f"Заказ №{self.pk} — {self.customer_name}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Заказ",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
        verbose_name="Товар",
    )
    product_name = models.CharField("Название товара", max_length=200)
    quantity = models.PositiveIntegerField("Количество")
    sizes = models.CharField("Размеры", max_length=200, blank=True)
    unit_price = models.PositiveIntegerField("Цена за единицу")

    class Meta:
        verbose_name = "позиция заказа"
        verbose_name_plural = "позиции заказа"

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"


class RestockRequest(models.Model):
    class Kind(models.TextChoices):
        NOTIFY = "notify", "Уведомить о поступлении"
        TAILOR = "tailor", "Пошить по меркам"
        VISIT = "visit", "Визит в ателье"

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="restock_requests",
        verbose_name="Товар",
    )
    size = models.CharField("Размер", max_length=20, blank=True)
    store = models.ForeignKey(
        Store,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="restock_requests",
        verbose_name="Точка",
    )
    kind = models.CharField(
        "Тип обращения",
        max_length=20,
        choices=Kind.choices,
        default=Kind.NOTIFY,
    )
    phone = models.CharField("Телефон", max_length=30)
    comment = models.TextField("Комментарий", blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="restock_requests",
        verbose_name="Покупатель",
    )
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "запрос в ателье"
        verbose_name_plural = "запросы в ателье"

    def __str__(self):
        return f"{self.product.name} — {self.get_kind_display()}"
