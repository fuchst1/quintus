from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("webapp", "0018_import_legacy_meters"),
    ]

    operations = [
        migrations.AddField(
            model_name="meter",
            name="unit_of_measure",
            field=models.CharField(
                choices=[("kwh", "kWh"), ("m3", "m³"), ("stk", "Stk")],
                default="kwh",
                help_text="Einheit, in der der Zählerstand erfasst wird (z. B. kWh oder m³).",
                max_length=10,
                verbose_name="Maßeinheit",
            ),
        ),
    ]
