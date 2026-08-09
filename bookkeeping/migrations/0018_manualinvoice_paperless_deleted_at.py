from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookkeeping", "0017_supportingdocument"),
    ]

    operations = [
        migrations.AddField(
            model_name="manualinvoice",
            name="paperless_deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="manualinvoice",
            name="paperless_status",
            field=models.CharField(
                choices=[
                    ("not_started", "Noch nicht übertragen"),
                    ("pending", "Übertragung zu Paperless läuft"),
                    ("completed", "In Paperless abgelegt"),
                    ("failed", "Übertragung fehlgeschlagen"),
                    ("deleted", "Aus Paperless gelöscht"),
                ],
                default="not_started",
                max_length=11,
            ),
        ),
    ]
