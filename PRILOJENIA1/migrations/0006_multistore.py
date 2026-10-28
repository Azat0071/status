import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

DEFAULT_STORES = (
    {
        "name": "Токтогула",
        "address": "ул. Токтогула, 87",
        "city": "Бишкек",
        "phone": "+996 312 90 12 08",
        "working_hours": "11:00–21:00",
        "is_default": True,
    },
    {
        "name": "Чуй",
        "address": "пр. Чуй, 155",
        "city": "Бишкек",
        "phone": "+996 312 90 44 71",
        "working_hours": "11:00–21:00",
        "is_default": False,
    },
)


def create_stores(apps, schema_editor):
    Store = apps.get_model("PRILOJENIA1", "Store")
    ProductSize = apps.get_model("PRILOJENIA1", "ProductSize")

    stores = [Store.objects.create(**data) for data in DEFAULT_STORES]
    ProductSize.objects.filter(store__isnull=True).update(store=stores[0])


def drop_stores(apps, schema_editor):
    Store = apps.get_model("PRILOJENIA1", "Store")
    Store.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("PRILOJENIA1", "0005_remove_customerprofile_phone_verified_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Store",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=80, verbose_name="Название")),
                ("address", models.CharField(max_length=200, verbose_name="Адрес")),
                (
                    "city",
                    models.CharField(
                        default="Бишкек", max_length=80, verbose_name="Город"
                    ),
                ),
                (
                    "phone",
                    models.CharField(blank=True, max_length=30, verbose_name="Телефон"),
                ),
                (
                    "working_hours",
                    models.CharField(
                        blank=True,
                        default="11:00–21:00",
                        max_length=60,
                        verbose_name="Часы работы",
                    ),
                ),
                (
                    "is_default",
                    models.BooleanField(
                        default=False, verbose_name="Точка по умолчанию"
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="Работает"),
                ),
            ],
            options={
                "verbose_name": "точка продаж",
                "verbose_name_plural": "точки продаж",
                "ordering": ("-is_default", "pk"),
            },
        ),
        migrations.AddField(
            model_name="productsize",
            name="store",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="sizes",
                to="PRILOJENIA1.store",
                verbose_name="Точка",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="store",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders",
                to="PRILOJENIA1.store",
                verbose_name="Точка самовывоза",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="productsize",
            name="unique_product_size",
        ),
        migrations.RunPython(create_stores, drop_stores),
        migrations.AlterField(
            model_name="productsize",
            name="store",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="sizes",
                to="PRILOJENIA1.store",
                verbose_name="Точка",
            ),
        ),
        migrations.AddConstraint(
            model_name="productsize",
            constraint=models.UniqueConstraint(
                fields=("product", "store", "size"),
                name="unique_product_store_size",
            ),
        ),
        migrations.CreateModel(
            name="RestockRequest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "size",
                    models.CharField(blank=True, max_length=20, verbose_name="Размер"),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("notify", "Уведомить о поступлении"),
                            ("tailor", "Пошить по меркам"),
                            ("visit", "Визит в ателье"),
                        ],
                        default="notify",
                        max_length=20,
                        verbose_name="Тип обращения",
                    ),
                ),
                ("phone", models.CharField(max_length=30, verbose_name="Телефон")),
                ("comment", models.TextField(blank=True, verbose_name="Комментарий")),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Создан"),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="restock_requests",
                        to="PRILOJENIA1.product",
                        verbose_name="Товар",
                    ),
                ),
                (
                    "store",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="restock_requests",
                        to="PRILOJENIA1.store",
                        verbose_name="Точка",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="restock_requests",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Покупатель",
                    ),
                ),
            ],
            options={
                "verbose_name": "запрос в ателье",
                "verbose_name_plural": "запросы в ателье",
                "ordering": ("-created_at",),
            },
        ),
    ]
