import uuid

from django.conf import settings
from django.db import models


def generate_phone_verification_token():
    return uuid.uuid4().hex


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


class ProductSize(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="sizes",
        verbose_name="Товар",
    )
    size = models.CharField("Размер", max_length=20)
    quantity = models.PositiveIntegerField("Количество на складе", default=0)

    class Meta:
        ordering = ("size",)
        constraints = [
            models.UniqueConstraint(
                fields=("product", "size"),
                name="unique_product_size",
            ),
        ]
        verbose_name = "остаток по размеру"
        verbose_name_plural = "остатки по размерам"

    def __str__(self):
        return f"{self.size}: {self.quantity}"


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
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
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
