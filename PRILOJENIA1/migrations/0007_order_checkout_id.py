from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("PRILOJENIA1", "0006_multistore"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="checkout_id",
            field=models.UUIDField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name="Группа оформления",
            ),
        ),
    ]
