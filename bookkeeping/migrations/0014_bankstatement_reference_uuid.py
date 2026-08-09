# Generated manually by Django migration workflow on 2026-08-09.

import uuid

from django.db import migrations, models


def assign_reference_uuids(apps, schema_editor):
    bank_statement_model = apps.get_model("bookkeeping", "BankStatement")
    statements = []
    for statement in bank_statement_model.objects.filter(
        reference_uuid__isnull=True
    ).only("pk"):
        statement.reference_uuid = uuid.uuid4()
        statements.append(statement)
    if statements:
        bank_statement_model.objects.bulk_update(
            statements,
            ["reference_uuid"],
            batch_size=1000,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("bookkeeping", "0013_bankstatement"),
    ]

    operations = [
        migrations.AddField(
            model_name="bankstatement",
            name="reference_uuid",
            field=models.UUIDField(
                blank=True,
                default=None,
                editable=False,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="bankstatement",
            name="paperless_reference_synced",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(
            assign_reference_uuids,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="bankstatement",
            name="reference_uuid",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
            ),
        ),
    ]
