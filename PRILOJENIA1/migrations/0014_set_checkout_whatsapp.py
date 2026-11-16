from django.db import migrations


WHATSAPP_URL = "https://wa.me/996504373851"
WHATSAPP_PHONE = "+996 504 373 851"


def set_checkout_whatsapp(apps, schema_editor):
    ContactSettings = apps.get_model("PRILOJENIA1", "SiteContactSettings")
    settings = ContactSettings.objects.filter(pk=1).first()
    if not settings:
        return

    updates = {}
    if not settings.whatsapp_url:
        updates["whatsapp_url"] = WHATSAPP_URL
    if settings.phone in ("", "+996 700 000 000"):
        updates["phone"] = WHATSAPP_PHONE
    if updates:
        ContactSettings.objects.filter(pk=settings.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [
        ("PRILOJENIA1", "0013_set_kievskaya_instagram"),
    ]

    operations = [
        migrations.RunPython(set_checkout_whatsapp, migrations.RunPython.noop),
    ]