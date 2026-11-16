from django.db import migrations


def set_kievskaya_instagram(apps, schema_editor):
    Store = apps.get_model("PRILOJENIA1", "Store")
    Store.objects.filter(name="Киевская").update(
        instagram_url="https://www.instagram.com/status.premiumm/",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("PRILOJENIA1", "0012_rename_stores_and_addresses"),
    ]

    operations = [
        migrations.RunPython(set_kievskaya_instagram, migrations.RunPython.noop),
    ]