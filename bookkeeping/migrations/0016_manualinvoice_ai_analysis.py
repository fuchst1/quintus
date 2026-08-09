from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookkeeping", "0015_manualinvoice_manualinvoiceentry"),
    ]

    operations = [
        migrations.AddField(
            model_name="manualinvoice",
            name="ai_status",
            field=models.CharField(
                choices=[
                    ("not_started", "Nicht analysiert"),
                    ("completed", "KI-Vorschlag erstellt"),
                    ("failed", "KI-Analyse fehlgeschlagen"),
                ],
                default="not_started",
                max_length=11,
            ),
        ),
        migrations.AddField(
            model_name="manualinvoice",
            name="ai_model_used",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="manualinvoice",
            name="ai_analyzed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="manualinvoice",
            name="ai_result",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="manualinvoice",
            name="ai_error",
            field=models.TextField(blank=True),
        ),
    ]
