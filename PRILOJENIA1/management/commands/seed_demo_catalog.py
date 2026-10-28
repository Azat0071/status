"""Демонстрационный каталог с остатками по двум точкам.

Команда нужна для проверки витрины: раскладывает несколько товаров
по точкам продаж. Удалить демо-данные: manage.py seed_demo_catalog --clear.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from PRILOJENIA1.models import Product, ProductSize, Store

DEMO_PRODUCTS = (
    {
        "sku": "ST-KN-104",
        "name": "Поло «Borgona»",
        "category": Product.Category.KNIT,
        "price": 18400,
        "description": (
            "Поло из плотного мериносового трикотажа цвета глубокого бордо. "
            "Полочка с потайной планкой, воротник держит форму."
        ),
        "image": "products/polo.jpg",
        "color": "Бордо",
        "material": "Мериносовый трикотаж 100%",
        "sizes": {
            "Токтогула": {"XS": 2, "S": 0, "M": 1, "L": 0, "XL": 3},
            "Чуй": {"XS": 0, "S": 2, "M": 0, "L": 4, "XL": 0},
        },
    },
    {
        "sku": "ST-BR-207",
        "name": "Брюки «Via Appia»",
        "category": Product.Category.PANTS,
        "price": 12900,
        "description": (
            "Брюки прямого силуэта из высокоплотного хлопка. "
            "Завышенная посадка, заутюженная складка."
        ),
        "image": "products/trousers.jpg",
        "color": "Белый",
        "material": "Высокоплотный хлопок",
        "sizes": {
            "Токтогула": {"46": 1, "48": 0, "50": 2, "52": 0},
            "Чуй": {"46": 0, "48": 1, "50": 0, "52": 2},
        },
    },
    {
        "sku": "ST-OU-311",
        "name": "Пальто «Portici»",
        "category": Product.Category.OUTER,
        "price": 46500,
        "description": (
            "Однобортное пальто из шерсти с кашемиром. "
            "Скрытая застёжка, подкладка из вискозы."
        ),
        "image": "products/coat.jpg",
        "color": "Графит",
        "material": "Шерсть и кашемир",
        "sizes": {
            "Токтогула": {"48": 1, "50": 1},
            "Чуй": {"52": 1, "54": 1},
        },
    },
    {
        "sku": "ST-SH-402",
        "name": "Лоферы «Duomo»",
        "category": Product.Category.SHOES,
        "price": 21800,
        "description": (
            "Лоферы из телячьей кожи на кожаной подошве. "
            "Мягкий задник, кожаная стелька."
        ),
        "image": "products/loafers.jpg",
        "color": "Чёрный",
        "material": "Телячья кожа",
        "sizes": {
            "Токтогула": {"39": 0, "40": 0, "41": 0, "42": 0, "43": 0},
            "Чуй": {"39": 0, "40": 0, "41": 1, "42": 2, "43": 0},
        },
    },
    {
        "sku": "ST-AC-508",
        "name": "Ремень «Torino»",
        "category": Product.Category.ACCESSORIES,
        "price": 6400,
        "description": (
            "Ремень из телячьей кожи с латунной пряжкой. "
            "Ширина 30 мм, срез обработан вручную."
        ),
        "image": "products/belt.jpg",
        "color": "Бордо",
        "material": "Телячья кожа",
        "sizes": {
            "Чуй": {"85": 1, "90": 2, "95": 0},
        },
    },
    {
        "sku": "ST-AC-512",
        "name": "Кашне «Como»",
        "category": Product.Category.ACCESSORIES,
        "price": 9200,
        "description": (
            "Кашне из тонкого кашемира с ручной бахромой. "
            "Размер 180 × 35 см."
        ),
        "image": "products/scarf.jpg",
        "color": "Серый",
        "material": "Кашемир 100%",
        "sizes": {
            "Токтогула": {"ONE SIZE": 0},
            "Чуй": {"ONE SIZE": 0},
        },
    },
)


class Command(BaseCommand):
    help = "Создаёт демонстрационные товары с остатками по точкам продаж"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Удалить демонстрационные товары",
        )

    def handle(self, *args, **options):
        skus = [row["sku"] for row in DEMO_PRODUCTS]

        if options["clear"]:
            deleted, _ = Product.objects.filter(sku__in=skus).delete()
            self.stdout.write(self.style.WARNING(f"Удалено объектов: {deleted}"))
            return

        stores = {store.name: store for store in Store.objects.all()}
        if not stores:
            raise CommandError(
                "Нет точек продаж. Создайте точки в админке или примените миграции."
            )

        with transaction.atomic():
            for row in DEMO_PRODUCTS:
                sizes = row["sizes"]
                product, _ = Product.objects.update_or_create(
                    sku=row["sku"],
                    defaults={
                        "name": row["name"],
                        "category": row["category"],
                        "price": row["price"],
                        "description": row["description"],
                        "image": row["image"],
                        "color": row["color"],
                        "material": row["material"],
                        "is_available": True,
                    },
                )
                product.sizes.all().delete()
                for store_name, size_map in sizes.items():
                    store = stores.get(store_name)
                    if store is None:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Точка «{store_name}» не найдена — пропущена."
                            )
                        )
                        continue
                    ProductSize.objects.bulk_create(
                        [
                            ProductSize(
                                product=product,
                                store=store,
                                size=size,
                                quantity=quantity,
                            )
                            for size, quantity in size_map.items()
                        ]
                    )

        self.stdout.write(
            self.style.SUCCESS(f"Демо-каталог готов: {len(DEMO_PRODUCTS)} товаров.")
        )
