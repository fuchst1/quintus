import re
from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase
from django.urls import resolve, reverse

from .models import BankStatement, BankTransaction, ManualInvoice, SupportingDocument
from .ui_components import (
    ComponentShowcaseView,
    STATUS_FAMILIES,
    STATUS_REGISTRY,
    UNKNOWN_STATUS,
    resolve_status,
)


class ComponentShowcaseRouteTests(SimpleTestCase):
    def test_components_route_is_namespaced_at_the_expected_url(self):
        url = reverse("bookkeeping_new_ui:components")

        self.assertEqual(url, "/bookkeeping/new-ui/components/")
        self.assertIs(resolve(url).func.view_class, ComponentShowcaseView)

    def test_components_showcase_renders_all_supported_statuses(self):
        response = self.client.get(reverse("bookkeeping_new_ui:components"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "bookkeeping/new_ui/component_showcase.html",
        )
        status_groups = response.context["status_groups"]
        self.assertEqual(len(status_groups), 6)
        self.assertEqual(
            sum(len(group["statuses"]) for group in status_groups),
            22,
        )
        self.assertEqual(
            response.context["showcase_breadcrumbs"],
            [
                {"label": "Buchhaltung", "url": "/bookkeeping/"},
                {"label": "Komponenten"},
            ],
        )
        for choices in STATUS_FAMILIES.values():
            for choice in choices:
                self.assertContains(response, str(choice.label))
        self.assertContains(response, "Unbekannter Fallback")
        self.assertContains(response, 'data-status-known="false"', count=2)
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'aria-selected="true"')
        self.assertContains(response, 'data-bs-target="#showcase-form-modal"')


class StatusRegistryTests(SimpleTestCase):
    expected_variants = {
        "bank_transaction": {
            "imported": "info",
            "matched": "info",
            "reviewed": "success",
            "booked": "success",
        },
        "manual_invoice": {
            "draft": "neutral",
            "ready": "success",
        },
        "manual_invoice_paperless": {
            "not_started": "neutral",
            "pending": "info",
            "completed": "success",
            "failed": "error",
            "deleted": "neutral",
        },
        "manual_invoice_ai": {
            "not_started": "neutral",
            "completed": "success",
            "failed": "error",
        },
        "bank_statement_paperless": {
            "pending": "info",
            "completed": "success",
            "duplicate": "success",
            "incomplete": "warning",
            "failed": "error",
        },
        "supporting_document_transfer": {
            "pending": "info",
            "completed": "success",
            "failed": "error",
        },
    }

    def test_registry_exactly_tracks_the_six_model_choice_families(self):
        expected_families = {
            "bank_transaction": BankTransaction.Status,
            "manual_invoice": ManualInvoice.Status,
            "manual_invoice_paperless": ManualInvoice.PaperlessStatus,
            "manual_invoice_ai": ManualInvoice.AIStatus,
            "bank_statement_paperless": BankStatement.PaperlessStatus,
            "supporting_document_transfer": SupportingDocument.TransferStatus,
        }

        self.assertEqual(STATUS_FAMILIES, expected_families)
        for family, choices in expected_families.items():
            self.assertEqual(
                list(STATUS_REGISTRY[family]),
                [choice.value for choice in choices],
            )
            for choice in choices:
                presentation = resolve_status(family, choice.value)
                self.assertEqual(presentation.label, str(choice.label))
                self.assertEqual(
                    presentation.variant,
                    self.expected_variants[family][choice.value],
                )
                self.assertTrue(presentation.known)

    def test_colliding_values_are_resolved_within_their_family(self):
        paperless_not_started = resolve_status(
            "manual_invoice_paperless",
            "not_started",
        )
        ai_not_started = resolve_status("manual_invoice_ai", "not_started")
        supporting_completed = resolve_status(
            "supporting_document_transfer",
            "completed",
        )
        invoice_completed = resolve_status(
            "manual_invoice_paperless",
            "completed",
        )

        self.assertEqual(paperless_not_started.label, "Noch nicht übertragen")
        self.assertEqual(ai_not_started.label, "Nicht analysiert")
        self.assertNotEqual(paperless_not_started.label, ai_not_started.label)
        self.assertEqual(supporting_completed.label, "Abgelegt")
        self.assertEqual(invoice_completed.label, "In Paperless abgelegt")

    def test_unknown_family_and_value_use_the_neutral_fallback(self):
        self.assertIs(resolve_status("bank_transaction", "future-status"), UNKNOWN_STATUS)
        self.assertIs(resolve_status("future-family", "completed"), UNKNOWN_STATUS)
        self.assertEqual(UNKNOWN_STATUS.label, "Unbekannt")
        self.assertEqual(UNKNOWN_STATUS.variant, "neutral")
        self.assertEqual(UNKNOWN_STATUS.icon, "bi-question-circle")
        self.assertFalse(UNKNOWN_STATUS.known)

    def test_status_badge_tag_renders_the_unknown_fallback(self):
        rendered = Template(
            "{% load bookkeeping_ui %}"
            "{% status_badge 'bank_transaction' missing_status %}"
        ).render(Context({"missing_status": "future-status"}))

        self.assertIn("Unbekannt", rendered)
        self.assertIn("bi-question-circle", rendered)
        self.assertIn("core-ledger-status--neutral", rendered)
        self.assertIn('data-status-variant="neutral"', rendered)


class CoreLedgerTokenTests(SimpleTestCase):
    def test_token_stylesheet_exactly_matches_the_canonical_design_values(self):
        token_path = (
            Path(__file__).parent
            / "static"
            / "bookkeeping"
            / "css"
            / "new_ui"
            / "tokens.css"
        )
        declarations = dict(
            re.findall(
                r"(--core-ledger-[\w-]+):\s*([^;]+);",
                token_path.read_text(encoding="utf-8"),
            )
        )
        expected = {
            "--core-ledger-color-navigation": "#041632",
            "--core-ledger-color-navigation-hover": "#102644",
            "--core-ledger-color-navigation-active": "#1b2b48",
            "--core-ledger-color-on-navigation": "#ffffff",
            "--core-ledger-color-on-navigation-muted": "#b7c7eb",
            "--core-ledger-color-primary": "#1b2b48",
            "--core-ledger-color-primary-hover": "#273a5d",
            "--core-ledger-color-primary-active": "#10213e",
            "--core-ledger-color-on-primary": "#ffffff",
            "--core-ledger-color-background": "#fbf8fb",
            "--core-ledger-color-surface": "#ffffff",
            "--core-ledger-color-surface-subtle": "#f5f3f6",
            "--core-ledger-color-surface-hover": "#efedf0",
            "--core-ledger-color-surface-selected": "#e5eaf3",
            "--core-ledger-color-text": "#1b1b1e",
            "--core-ledger-color-text-muted": "#545f72",
            "--core-ledger-color-text-subtle": "#75777e",
            "--core-ledger-color-text-inverse": "#ffffff",
            "--core-ledger-color-border": "#d5d4da",
            "--core-ledger-color-border-strong": "#b8bac2",
            "--core-ledger-color-focus": "#4f5e7e",
            "--core-ledger-color-success": "#2d6a4f",
            "--core-ledger-color-success-container": "#dcefe5",
            "--core-ledger-color-on-success-container": "#194c36",
            "--core-ledger-color-warning": "#8a5a00",
            "--core-ledger-color-warning-container": "#fff0cc",
            "--core-ledger-color-on-warning-container": "#684300",
            "--core-ledger-color-error": "#ba1a1a",
            "--core-ledger-color-error-container": "#ffdad6",
            "--core-ledger-color-on-error-container": "#93000a",
            "--core-ledger-color-info": "#315b8a",
            "--core-ledger-color-info-container": "#dce9f7",
            "--core-ledger-color-on-info-container": "#24496f",
            "--core-ledger-font-family": (
                'Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", '
                "sans-serif"
            ),
            "--core-ledger-display-lg-font-size": "30px",
            "--core-ledger-display-lg-font-weight": "700",
            "--core-ledger-display-lg-line-height": "38px",
            "--core-ledger-display-lg-letter-spacing": "-0.02em",
            "--core-ledger-headline-md-font-size": "24px",
            "--core-ledger-headline-md-font-weight": "600",
            "--core-ledger-headline-md-line-height": "32px",
            "--core-ledger-headline-md-letter-spacing": "-0.01em",
            "--core-ledger-title-sm-font-size": "18px",
            "--core-ledger-title-sm-font-weight": "600",
            "--core-ledger-title-sm-line-height": "24px",
            "--core-ledger-body-md-font-size": "14px",
            "--core-ledger-body-md-font-weight": "400",
            "--core-ledger-body-md-line-height": "20px",
            "--core-ledger-body-sm-font-size": "13px",
            "--core-ledger-body-sm-font-weight": "400",
            "--core-ledger-body-sm-line-height": "18px",
            "--core-ledger-data-table-font-size": "13px",
            "--core-ledger-data-table-font-weight": "400",
            "--core-ledger-data-table-line-height": "16px",
            "--core-ledger-form-label-font-size": "13px",
            "--core-ledger-form-label-font-weight": "600",
            "--core-ledger-form-label-line-height": "18px",
            "--core-ledger-form-label-text-transform": "none",
            "--core-ledger-label-caps-font-size": "11px",
            "--core-ledger-label-caps-font-weight": "700",
            "--core-ledger-label-caps-line-height": "16px",
            "--core-ledger-label-caps-letter-spacing": "0.05em",
            "--core-ledger-label-caps-text-transform": "uppercase",
            "--core-ledger-radius-sm": "2px",
            "--core-ledger-radius-default": "4px",
            "--core-ledger-radius-md": "6px",
            "--core-ledger-radius-lg": "8px",
            "--core-ledger-radius-xl": "12px",
            "--core-ledger-radius-full": "9999px",
            "--core-ledger-space-base": "4px",
            "--core-ledger-space-xs": "4px",
            "--core-ledger-space-sm": "8px",
            "--core-ledger-space-md": "16px",
            "--core-ledger-space-lg": "24px",
            "--core-ledger-space-xl": "32px",
            "--core-ledger-space-gutter": "16px",
            "--core-ledger-margin-mobile": "16px",
            "--core-ledger-margin-tablet": "24px",
            "--core-ledger-margin-desktop": "32px",
            "--core-ledger-sidebar-width": "240px",
            "--core-ledger-sidebar-rail-width": "64px",
            "--core-ledger-content-max-width": "none",
            "--core-ledger-breakpoint-desktop": "1280px",
            "--core-ledger-breakpoint-tablet": "768px",
            "--core-ledger-breakpoint-mobile": "768px",
        }

        self.assertEqual(declarations, expected)
