from django.db import migrations


CHUY_INSTAGRAM_URL = "https://www.instagram.com/status.kgg1/"


def rename_stores(apps, schema_editor):
    Store = apps.get_model("PRILOJENIA1", "Store")
    former_toktogula = Store.objects.filter(name="Токтогула").order_by("pk").first()
    former_chuy = Store.objects.filter(name="Чуй").order_by("pk").first()

    if former_toktogula:
        Store.objects.filter(pk=former_toktogula.pk).update(
            name="Чуй",
            address="пр. Чуй, 322",
            is_default=True,
            instagram_url=CHUY_INSTAGRAM_URL,
        )

    if former_chuy and (not former_toktogula or former_chuy.pk != former_toktogula.pk):
        Store.objects.filter(pk=former_chuy.pk).update(
            name="Киевская",
            address="ул. Киевская, 168",
            is_default=False,
            instagram_url="",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("PRILOJENIA1", "0011_store_instagram_url_and_more"),
    ]

    operations = [
        migrations.RunPython(rename_stores, migrations.RunPython.noop),
    ]