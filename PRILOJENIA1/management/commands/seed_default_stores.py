from django.core.management.base import BaseCommand

from PRILOJENIA1.models import Store

DEFAULT_STORES = (
    {
        "name": "Чуй",
        "address": "пр. Чуй, 322",
        "city": "Бишкек",
        "phone": "+996 312 90 12 08",
        "working_hours": "11:00–21:00",
        "is_default": True,
        "is_active": True,
    },
    {
        "name": "Киевская",
        "address": "ул. Киевская, 168",
        "city": "Бишкек",
        "phone": "+996 312 90 44 71",
        "working_hours": "11:00–21:00",
        "is_default": False,
        "is_active": True,
    },
)


class Command(BaseCommand):
    help = "Создаёт и восстанавливает две точки продаж магазина, если они отсутствуют."

    def handle(self, *args, **options):
        created = 0
        for data in DEFAULT_STORES:
            store, was_created = Store.objects.get_or_create(
                name=data["name"],
                defaults={
                    "address": data["address"],
                    "city": data["city"],
                    "phone": data["phone"],
                    "working_hours": data["working_hours"],
                    "is_default": data["is_default"],
                    "is_active": data["is_active"],
                },
            )
            if was_created:
                created += 1
            for field, value in data.items():
                if field == "name":
                    continue
                setattr(store, field, value)
            store.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Точки продаж готовы: {Store.objects.filter(is_active=True).count()} активных."
            )
        )
        if created:
            self.stdout.write(self.style.WARNING(f"Создано новых точек: {created}."))
