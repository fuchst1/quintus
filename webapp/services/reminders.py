from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from calendar import monthrange
from typing import Iterable

from django.utils import timezone

from webapp.models import LeaseAgreement, ReminderRuleConfig


def add_months(input_date: date, months: int) -> date:
    if months < 0:
        raise ValueError("months must be >= 0")
    year = input_date.year + (input_date.month - 1 + months) // 12
    month = (input_date.month - 1 + months) % 12 + 1
    day = min(input_date.day, monthrange(year, month)[1])
    return date(year, month, day)


@dataclass(slots=True)
class ReminderItem:
    rule_code: str
    rule_title: str
    lead_months: int
    lease: LeaseAgreement
    due_date: date
    recipient_email: str
    is_overdue: bool
    days_until_due: int

    @property
    def lease_id(self) -> int:
        return int(self.lease.pk)

    @property
    def lease_label(self) -> str:
        property_name = ""
        unit_name = ""
        if self.lease.unit and self.lease.unit.property:
            property_name = self.lease.unit.property.name
        if self.lease.unit:
            unit_name = self.lease.unit.name
        if property_name and unit_name:
            return f"{property_name} · {unit_name}"
        return unit_name or property_name or "Ohne Einheit"

    @property
    def tenant_label(self) -> str:
        names = [
            f"{tenant.first_name} {tenant.last_name}".strip()
            for tenant in self.lease.tenants.all()
        ]
        names = [name for name in names if name]
        return ", ".join(names) if names else "Kein Mieter hinterlegt"

    @property
    def due_status_label(self) -> str:
        if self.days_until_due < 0:
            days = abs(self.days_until_due)
            return f"Überfällig seit {days} Tag(en)"
        if self.days_until_due == 0:
            return "Heute fällig"
        return f"Fällig in {self.days_until_due} Tag(en)"


class ReminderRule(ABC):
    code: str

    @abstractmethod
    def queryset(self):
        raise NotImplementedError

    @abstractmethod
    def due_date_for_lease(self, lease: LeaseAgreement) -> date | None:
        raise NotImplementedError

    def collect(self, *, config: ReminderRuleConfig, today: date) -> list[ReminderItem]:
        horizon = add_months(today, config.lead_months)
        items: list[ReminderItem] = []
        leases = self.queryset().select_related("unit", "unit__property", "manager").prefetch_related("tenants")

        for lease in leases:
            due_date = self.due_date_for_lease(lease)
            if due_date is None or due_date > horizon:
                continue
            recipient = ""
            if lease.manager and lease.manager.email:
                recipient = lease.manager.email.strip()
            delta_days = (due_date - today).days
            items.append(
                ReminderItem(
                    rule_code=config.code,
                    rule_title=config.title,
                    lead_months=config.lead_months,
                    lease=lease,
                    due_date=due_date,
                    recipient_email=recipient,
                    is_overdue=due_date < today,
                    days_until_due=delta_days,
                )
            )

        items.sort(
            key=lambda item: (
                item.due_date,
                item.lease.unit.property.name if item.lease.unit and item.lease.unit.property else "",
                item.lease.unit.name if item.lease.unit else "",
                item.lease_id,
            )
        )
        return items


class VpiIndexationRule(ReminderRule):
    code = "vpi_indexation"

    def queryset(self):
        return LeaseAgreement.objects.filter(
            status=LeaseAgreement.Status.AKTIV,
            index_type=LeaseAgreement.IndexType.VPI,
            last_index_adjustment__isnull=False,
        )

    def due_date_for_lease(self, lease: LeaseAgreement) -> date | None:
        if lease.last_index_adjustment is None:
            return None
        return add_months(lease.last_index_adjustment, 12)


class LeaseExitRule(ReminderRule):
    code = "lease_exit"

    def queryset(self):
        return LeaseAgreement.objects.filter(
            status=LeaseAgreement.Status.AKTIV,
            exit_date__isnull=False,
        )

    def due_date_for_lease(self, lease: LeaseAgreement) -> date | None:
        return lease.exit_date


class ReminderService:
    def __init__(self, *, today: date | None = None):
        self.today = today or timezone.localdate()
        self._rules = {
            rule.code: rule
            for rule in (
                VpiIndexationRule(),
                LeaseExitRule(),
            )
        }

    def collect_items(self) -> list[ReminderItem]:
        items: list[ReminderItem] = []
        configs = ReminderRuleConfig.objects.filter(is_active=True).order_by("sort_order", "code")
        for config in configs:
            rule = self._rules.get(config.code)
            if rule is None:
                continue
            items.extend(rule.collect(config=config, today=self.today))

        items.sort(
            key=lambda item: (
                item.due_date,
                item.rule_title.lower(),
                item.lease.unit.property.name if item.lease.unit and item.lease.unit.property else "",
                item.lease.unit.name if item.lease.unit else "",
                item.lease_id,
            )
        )
        return items

    @staticmethod
    def items_by_lease(items: Iterable[ReminderItem]) -> dict[int, list[ReminderItem]]:
        grouped: dict[int, list[ReminderItem]] = {}
        for item in items:
            grouped.setdefault(item.lease_id, []).append(item)
        for lease_items in grouped.values():
            lease_items.sort(key=lambda entry: (entry.due_date, entry.rule_title.lower()))
        return grouped

    @staticmethod
    def items_by_recipient(items: Iterable[ReminderItem]) -> dict[str, list[ReminderItem]]:
        grouped: dict[str, list[ReminderItem]] = {}
        for item in items:
            recipient = (item.recipient_email or "").strip().lower()
            if not recipient:
                continue
            grouped.setdefault(recipient, []).append(item)
        for recipient_items in grouped.values():
            recipient_items.sort(key=lambda entry: (entry.due_date, entry.rule_title.lower(), entry.lease_id))
        return grouped

    @staticmethod
    def build_summary(items: Iterable[ReminderItem]) -> dict[str, int]:
        items_list = list(items)
        return {
            "total": len(items_list),
            "overdue": sum(1 for item in items_list if item.is_overdue),
            "without_email": sum(1 for item in items_list if not item.recipient_email),
        }

    @staticmethod
    def top_items(items: Iterable[ReminderItem], *, limit: int = 8) -> list[ReminderItem]:
        items_list = list(items)
        return items_list[:limit]
