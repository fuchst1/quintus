import uuid

from django.db import migrations, models


def add_source_uuid_column_if_missing(apps, schema_editor):
    MeterReading = apps.get_model("webapp", "MeterReading")
    table_name = MeterReading._meta.db_table
    with schema_editor.connection.cursor() as cursor:
        existing_columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor,
                table_name,
            )
        }

    if "source_uuid" in existing_columns:
        return

    field = models.UUIDField(
        db_index=True,
        editable=False,
        null=True,
        verbose_name="Quellreferenz",
    )
    field.set_attributes_from_name("source_uuid")
    field.model = MeterReading
    schema_editor.add_field(MeterReading, field)


def populate_meterreading_source_uuid(apps, schema_editor):
    MeterReading = apps.get_model("webapp", "MeterReading")
    batch = []
    queryset = MeterReading.objects.all().only("pk")

    for reading in queryset.iterator(chunk_size=200):
        reading.source_uuid = uuid.uuid4()
        batch.append(reading)
        if len(batch) >= 200:
            MeterReading.objects.bulk_update(batch, ["source_uuid"], batch_size=200)
            batch.clear()

    if batch:
        MeterReading.objects.bulk_update(batch, ["source_uuid"], batch_size=200)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("webapp", "0052_vpiadjustmentrun_brief_freitext_parking"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    add_source_uuid_column_if_missing,
                    migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="meterreading",
                    name="source_uuid",
                    field=models.UUIDField(
                        db_index=True,
                        editable=False,
                        null=True,
                        verbose_name="Quellreferenz",
                    ),
                ),
            ],
        ),
        migrations.RunPython(
            populate_meterreading_source_uuid,
            migrations.RunPython.noop,
        ),
        migrations.RunSQL(
            sql='DROP TABLE IF EXISTS "new__webapp_meterreading";',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name="meterreading",
            name="source_uuid",
            field=models.UUIDField(
                db_index=True,
                default=uuid.uuid4,
                editable=False,
                unique=True,
                verbose_name="Quellreferenz",
            ),
        ),
    ]
