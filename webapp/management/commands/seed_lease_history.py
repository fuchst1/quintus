from django.core.management.base import BaseCommand

from webapp.models import LeaseAgreement


class Command(BaseCommand):
    help = "Erzeugt initiale Historie für bestehende Mietverträge."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Zeigt nur, wie viele Einträge erzeugt würden.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        leases = LeaseAgreement.objects.all().prefetch_related("tenants")

        total = leases.count()
        to_seed = 0
        created = 0

        for lease in leases:
            if lease.history.exists():
                continue
            to_seed += 1
            if dry_run:
                continue
            lease._change_reason = "Initialer Stand"
            lease.save()
            created += 1

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry-Run: {to_seed} von {total} Mietverträgen würden initialisiert werden."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Initialisiert: {created} von {total} Mietverträgen mit Historie."
            )
        )
