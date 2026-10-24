from django.db import models


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
