from django.db import migrations


def seed_reminder_rules(apps, schema_editor):
    ReminderRuleConfig = apps.get_model("webapp", "ReminderRuleConfig")
    defaults = [
        {
            "code": "vpi_indexation",
            "title": "VPI-Indexierung",
            "lead_months": 2,
            "is_active": True,
            "sort_order": 10,
        },
        {
            "code": "lease_exit",
            "title": "Vertragsende",
            "lead_months": 3,
            "is_active": True,
            "sort_order": 20,
        },
    ]
    for item in defaults:
        ReminderRuleConfig.objects.update_or_create(
            code=item["code"],
            defaults={
                "title": item["title"],
                "lead_months": item["lead_months"],
                "is_active": item["is_active"],
                "sort_order": item["sort_order"],
            },
        )


def unseed_reminder_rules(apps, schema_editor):
    ReminderRuleConfig = apps.get_model("webapp", "ReminderRuleConfig")
    ReminderRuleConfig.objects.filter(code__in=["vpi_indexation", "lease_exit"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("webapp", "0041_reminderruleconfig_reminderemaillog"),
    ]

    operations = [
        migrations.RunPython(seed_reminder_rules, unseed_reminder_rules),
    ]
