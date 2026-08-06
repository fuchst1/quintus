from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("bookkeeping", "0003_banktransaction_matched_rule"),
    ]

    operations = [
        migrations.RenameField(
            model_name="matchingrule",
            old_name="expected_monthly_amount",
            new_name="expected_amount",
        ),
    ]
