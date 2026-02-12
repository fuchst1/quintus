from __future__ import annotations

from datetime import date, datetime, timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from webapp.models import ReminderEmailLog
from webapp.services.reminders import ReminderItem, ReminderService


class Command(BaseCommand):
    help = "Versendet Erinnerungen als Sammelmail je Empfänger (idempotent pro Kalenderwoche)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--today",
            type=str,
            help="Bezugsdatum im Format YYYY-MM-DD (optional, für Tests).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Nur anzeigen, was versendet würde, ohne E-Mails/Logs zu schreiben.",
        )

    def handle(self, *args, **options):
        today = self._parse_today(options.get("today"))
        dry_run = bool(options.get("dry_run"))
        period_start = today - timedelta(days=today.weekday())

        reminder_service = ReminderService(today=today)
        items = reminder_service.collect_items()
        grouped = reminder_service.items_by_recipient(items)
        missing_recipient_count = sum(1 for item in items if not item.recipient_email)

        recipient_mail_count = 0
        recipient_skipped_existing = 0
        item_mail_count = 0

        for recipient_email, recipient_items in grouped.items():
            existing_keys = set(
                ReminderEmailLog.objects.filter(
                    period_start=period_start,
                    recipient_email=recipient_email,
                ).values_list("rule_code", "lease_id", "due_date")
            )
            pending_items = [
                item
                for item in recipient_items
                if (item.rule_code, item.lease_id, item.due_date) not in existing_keys
            ]
            if not pending_items:
                recipient_skipped_existing += 1
                continue

            if dry_run:
                recipient_mail_count += 1
                item_mail_count += len(pending_items)
                continue

            subject, body = self._build_email(
                period_start=period_start,
                recipient_email=recipient_email,
                pending_items=pending_items,
            )
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                fail_silently=False,
            )

            with transaction.atomic():
                ReminderEmailLog.objects.bulk_create(
                    [
                        ReminderEmailLog(
                            period_start=period_start,
                            recipient_email=recipient_email,
                            rule_code=item.rule_code,
                            lease=item.lease,
                            due_date=item.due_date,
                        )
                        for item in pending_items
                    ],
                    ignore_conflicts=True,
                )

            recipient_mail_count += 1
            item_mail_count += len(pending_items)

        mode_text = "Dry-Run" if dry_run else "Versand"
        self.stdout.write(
            self.style.SUCCESS(
                (
                    f"{mode_text} abgeschlossen. "
                    f"Datum: {today.isoformat()}, Periode ab: {period_start.isoformat()}, "
                    f"Empfängergruppen: {len(grouped)}, "
                    f"Mails: {recipient_mail_count}, "
                    f"Erinnerungen in Mails: {item_mail_count}, "
                    f"Ohne Empfänger: {missing_recipient_count}, "
                    f"Bereits versendet (diese Woche): {recipient_skipped_existing}."
                )
            )
        )

    @staticmethod
    def _parse_today(value: str | None) -> date:
        if not value:
            return timezone.localdate()
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (TypeError, ValueError) as exc:
            raise CommandError("Ungültiges Datum. Erwartet: YYYY-MM-DD") from exc

    @staticmethod
    def _build_email(
        *,
        period_start: date,
        recipient_email: str,
        pending_items: list[ReminderItem],
    ) -> tuple[str, str]:
        subject = (
            "[Quintus] Erinnerungen "
            f"ab {period_start.strftime('%d.%m.%Y')} "
            f"({len(pending_items)} offen)"
        )
        lines = [
            "Guten Tag,",
            "",
            "folgende Erinnerungen sind derzeit offen:",
            "",
        ]
        for index, item in enumerate(pending_items, start=1):
            lines.append(
                (
                    f"{index}. {item.rule_title}: {item.lease_label}"
                    f" | Mieter: {item.tenant_label}"
                    f" | Termin: {item.due_date.strftime('%d.%m.%Y')}"
                    f" | Status: {item.due_status_label}"
                )
            )

        lines.extend(
            [
                "",
                "Diese E-Mail wurde automatisch von Quintus erstellt.",
                f"Empfänger: {recipient_email}",
            ]
        )
        return subject, "\n".join(lines)
