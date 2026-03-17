import uuid

from django.db import migrations, models


def populate_betriebskostenbeleg_source_uuid(apps, schema_editor):
    BetriebskostenBeleg = apps.get_model("webapp", "BetriebskostenBeleg")
    batch = []
    queryset = BetriebskostenBeleg.objects.filter(source_uuid__isnull=True).only("pk")

    for beleg in queryset.iterator(chunk_size=200):
        beleg.source_uuid = uuid.uuid4()
        batch.append(beleg)
        if len(batch) >= 200:
            BetriebskostenBeleg.objects.bulk_update(batch, ["source_uuid"], batch_size=200)
            batch.clear()

    if batch:
        BetriebskostenBeleg.objects.bulk_update(batch, ["source_uuid"], batch_size=200)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("webapp", "0053_meterreading_source_uuid"),
    ]

    operations = [
        migrations.AddField(
            model_name="betriebskostenbeleg",
            name="paperless_document_id",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="Paperless-Dokument-ID",
            ),
        ),
        migrations.AddField(
            model_name="betriebskostenbeleg",
            name="paperless_task_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Paperless-Task-ID",
            ),
        ),
        migrations.AddField(
            model_name="betriebskostenbeleg",
            name="source_uuid",
            field=models.UUIDField(
                db_index=True,
                editable=False,
                null=True,
                verbose_name="Quellreferenz",
            ),
        ),
        migrations.RunPython(
            populate_betriebskostenbeleg_source_uuid,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="betriebskostenbeleg",
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
