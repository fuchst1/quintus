import io
import tempfile
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from .workflow_reset import build_reset_selection, execute_workflow_reset
from .paperless import PaperlessClient
from .models import (
    BankTransaction,
    BookingEntry,
    ManualInvoice,
    ManualInvoiceEntry,
    MatchingRule,
    MatchingRuleBookingTemplate,
    SupportingDocument,
)


class WorkflowResetCommandTests(TestCase):
    """The guarded command only removes reproducible booking artifacts."""

    def setUp(self):
        self.rule = MatchingRule.objects.create(
            name="Reset-Testregel",
            direction=MatchingRule.Direction.OUTGOING,
            match_type=MatchingRule.MatchType.REGEX,
            text_pattern="Reset-Test",
        )
        self.template = MatchingRuleBookingTemplate.objects.create(
            matching_rule=self.rule,
            position=1,
            booking_text="Automatisch erzeugter Satz",
            category="7600",
        )
        self.transaction = BankTransaction.objects.create(
            source_hash=uuid.uuid4().hex * 2,
            booking_date=date(2026, 8, 1),
            value_date=date(2026, 8, 1),
            partner_name="Reset-Test",
            partner_iban="AT611904300234573201",
            amount=Decimal("-12.34"),
            purpose="Originaler Verwendungszweck",
            direction=BankTransaction.Direction.OUTGOING,
            status=BankTransaction.Status.REVIEWED,
            matched_rule=self.rule,
        )
        self.bank_entry = BookingEntry.objects.create(
            bank_transaction=self.transaction,
            payment_date=date(2026, 8, 1),
            booking_text="Automatisch erzeugter Satz",
            partner_name="Reset-Test",
            gross_amount=Decimal("-12.34"),
            matching_rule_template=self.template,
        )
        self.invoice = ManualInvoice.objects.create(
            file_hash=uuid.uuid4().hex * 2,
            status=ManualInvoice.Status.READY,
            paperless_task_id="paperless-task-222",
            paperless_document_id=222,
            paperless_status=ManualInvoice.PaperlessStatus.COMPLETED,
            paperless_error="",
            partner_name="Reset-Rechnung",
            gross_amount=Decimal("12.34"),
        )
        self.manual_entry = ManualInvoiceEntry.objects.create(
            manual_invoice=self.invoice,
            payment_date=date(2026, 8, 1),
            booking_text="Manueller Satz",
            partner_name="Reset-Rechnung",
            gross_amount=Decimal("12.34"),
        )
        self.supporting_document = SupportingDocument.objects.create(
            bank_transaction=self.transaction,
            original_filename="original.pdf",
            paperless_document_id=333,
            transfer_status=SupportingDocument.TransferStatus.COMPLETED,
        )

    def test_default_command_is_dry_run_and_lists_derived_rows(self):
        output = io.StringIO()

        call_command("reset_bookkeeping_workflow", stdout=output)

        text = output.getvalue()
        self.assertIn("DRY-RUN", text)
        self.assertIn("BookingEntry: 1", text)
        self.assertIn("ManualInvoiceEntry: 1", text)
        self.transaction.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(self.transaction.status, BankTransaction.Status.REVIEWED)
        self.assertEqual(self.transaction.matched_rule_id, self.rule.pk)
        self.assertTrue(BookingEntry.objects.filter(pk=self.bank_entry.pk).exists())
        self.assertTrue(ManualInvoiceEntry.objects.filter(pk=self.manual_entry.pk).exists())
        self.assertEqual(self.invoice.status, ManualInvoice.Status.READY)

    def test_execute_requires_exact_confirmation_before_touching_data(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(CommandError):
                call_command(
                    "reset_bookkeeping_workflow",
                    "--execute",
                    "--confirm",
                    "wrong-token",
                    "--backup-path",
                    str(Path(directory) / "backup.sqlite3"),
                )

        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.status, BankTransaction.Status.REVIEWED)
        self.assertTrue(BookingEntry.objects.filter(pk=self.bank_entry.pk).exists())

    def test_existing_backup_path_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            backup_path = Path(directory) / "already-there.sqlite3"
            backup_path.write_bytes(b"original-backup")
            with patch(
                "bookkeeping.management.commands.reset_bookkeeping_workflow.database_path",
                return_value=Path(__file__).resolve(),
            ), self.assertRaises(CommandError):
                call_command(
                    "reset_bookkeeping_workflow",
                    "--execute",
                    "--confirm",
                    "RESET-BOOKKEEPING-WORKFLOW",
                    "--backup-path",
                    str(backup_path),
                )
            self.assertEqual(backup_path.read_bytes(), b"original-backup")

    def test_execute_resets_derived_data_and_preserves_sources_and_paperless(self):
        original_hash = self.transaction.source_hash
        original_invoice_uuid = self.invoice.reference_uuid

        result = execute_workflow_reset(build_reset_selection())
        self.transaction.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(self.transaction.status, BankTransaction.Status.IMPORTED)
        self.assertIsNone(self.transaction.matched_rule_id)
        self.assertEqual(self.transaction.source_hash, original_hash)
        self.assertFalse(BookingEntry.objects.filter(pk=self.bank_entry.pk).exists())
        self.assertEqual(self.invoice.status, ManualInvoice.Status.DRAFT)
        self.assertEqual(self.invoice.reference_uuid, original_invoice_uuid)
        self.assertEqual(self.invoice.paperless_document_id, 222)
        self.assertEqual(
            self.invoice.paperless_status,
            ManualInvoice.PaperlessStatus.COMPLETED,
        )
        self.assertFalse(ManualInvoiceEntry.objects.filter(pk=self.manual_entry.pk).exists())
        self.assertTrue(SupportingDocument.objects.filter(pk=self.supporting_document.pk).exists())
        self.assertTrue(MatchingRule.objects.filter(pk=self.rule.pk).exists())
        self.assertTrue(MatchingRuleBookingTemplate.objects.filter(pk=self.template.pk).exists())
        self.assertEqual(result.deleted["BookingEntry"], 1)
        self.assertEqual(result.deleted["ManualInvoiceEntry"], 1)

    def test_backup_failure_leaves_database_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            backup_path = Path(directory) / "workflow-before-reset.sqlite3"
            with patch(
                "bookkeeping.management.commands.reset_bookkeeping_workflow.database_path",
                return_value=Path(__file__).resolve(),
            ), patch(
                "bookkeeping.management.commands.reset_bookkeeping_workflow.Command._create_and_verify_backup",
                side_effect=CommandError("simulierter Backup-Fehler"),
            ), self.assertRaises(CommandError):
                call_command(
                    "reset_bookkeeping_workflow",
                    "--execute",
                    "--confirm",
                    "RESET-BOOKKEEPING-WORKFLOW",
                    "--backup-path",
                    str(backup_path),
                )

        self.transaction.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(self.transaction.status, BankTransaction.Status.REVIEWED)
        self.assertEqual(self.transaction.matched_rule_id, self.rule.pk)
        self.assertEqual(self.invoice.status, ManualInvoice.Status.READY)
        self.assertTrue(BookingEntry.objects.filter(pk=self.bank_entry.pk).exists())
        self.assertTrue(ManualInvoiceEntry.objects.filter(pk=self.manual_entry.pk).exists())

    def test_reset_error_rolls_back_deletions_and_status_changes(self):
        with patch(
            "bookkeeping.workflow_reset._assert_reset_state",
            side_effect=RuntimeError("simulierter Reset-Fehler"),
        ), self.assertRaises(RuntimeError):
            execute_workflow_reset(build_reset_selection())

        self.transaction.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(self.transaction.status, BankTransaction.Status.REVIEWED)
        self.assertEqual(self.transaction.matched_rule_id, self.rule.pk)
        self.assertEqual(self.invoice.status, ManualInvoice.Status.READY)
        self.assertTrue(BookingEntry.objects.filter(pk=self.bank_entry.pk).exists())
        self.assertTrue(ManualInvoiceEntry.objects.filter(pk=self.manual_entry.pk).exists())

    def test_reset_never_calls_paperless(self):
        with patch.object(PaperlessClient, "upload_bank_statement") as upload_statement, patch.object(
            PaperlessClient, "upload_manual_invoice"
        ) as upload_invoice, patch.object(
            PaperlessClient, "upload_supporting_document"
        ) as upload_supporting:
            execute_workflow_reset(build_reset_selection())

        upload_statement.assert_not_called()
        upload_invoice.assert_not_called()
        upload_supporting.assert_not_called()


class WorkflowResetFinalizedGuardTests(TestCase):
    def test_booked_transactions_require_second_confirmation(self):
        transaction = BankTransaction.objects.create(
            booking_date=date(2026, 8, 1),
            amount=Decimal("-1.00"),
            direction=BankTransaction.Direction.OUTGOING,
            status=BankTransaction.Status.BOOKED,
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(CommandError):
                call_command(
                    "reset_bookkeeping_workflow",
                    "--execute",
                    "--confirm",
                    "RESET-BOOKKEEPING-WORKFLOW",
                    "--backup-path",
                    str(Path(directory) / "backup.sqlite3"),
                )
        transaction.refresh_from_db()
        self.assertEqual(transaction.status, BankTransaction.Status.BOOKED)
