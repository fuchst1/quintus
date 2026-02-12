from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string


class AnnualStatementPdfGenerationError(RuntimeError):
    """Eindeutiger Fehler für fehlgeschlagene BK-PDF-Erstellung."""


class AnnualStatementPdfService:
    """Erzeugt BK-Briefe primär über WeasyPrint (HTML -> PDF)."""

    logger = logging.getLogger(__name__)
    _LETTER_CSS_CACHE: str | None = None
    _WEASYPRINT_RUNTIME_OK: bool | None = None

    @classmethod
    def _load_letter_css(cls) -> str:
        if cls._LETTER_CSS_CACHE is not None:
            return cls._LETTER_CSS_CACHE

        css_path = Path(settings.BASE_DIR) / "webapp" / "static" / "webapp" / "css" / "letters.css"
        try:
            cls._LETTER_CSS_CACHE = css_path.read_text(encoding="utf-8")
        except OSError:
            cls._LETTER_CSS_CACHE = """
            body { font-family: 'DejaVu Sans', sans-serif; font-size: 11pt; color: #1d2330; }
            .letter-wrap { max-width: 180mm; margin: 0 auto; }
            .letter-head { display: flex; justify-content: space-between; margin-bottom: 14mm; }
            .letter-table { width: 100%; border-collapse: collapse; margin: 8mm 0; }
            .letter-table th, .letter-table td { border: 1px solid #ccd3de; padding: 6px 8px; }
            .text-right { text-align: right; }
            """
        return cls._LETTER_CSS_CACHE

    @staticmethod
    def weasyprint_available() -> bool:
        if AnnualStatementPdfService._WEASYPRINT_RUNTIME_OK is not None:
            return AnnualStatementPdfService._WEASYPRINT_RUNTIME_OK

        try:
            AnnualStatementPdfService._patch_pydyf_compat()
            from weasyprint import HTML  # noqa: F401

            # Runtime-Check statt reiner Importprüfung, damit API-Inkompatibilitäten
            # zwischen weasyprint/pydyf früh erkannt werden.
            HTML(string="<html><body>ok</body></html>").write_pdf()
        except Exception:
            AnnualStatementPdfService._WEASYPRINT_RUNTIME_OK = False
            return False
        AnnualStatementPdfService._WEASYPRINT_RUNTIME_OK = True
        return True

    @staticmethod
    def _patch_pydyf_compat() -> None:
        """Shims für pydyf >= 0.12, damit ältere WeasyPrint-Versionen weiterhin laufen."""
        try:
            import pydyf
        except Exception:
            return

        if not hasattr(pydyf.Stream, "transform") and hasattr(pydyf.Stream, "set_matrix"):
            def _transform(self, a=1, b=0, c=0, d=1, e=0, f=0):
                return self.set_matrix(a, b, c, d, e, f)

            pydyf.Stream.transform = _transform

        if not hasattr(pydyf.Stream, "text_matrix") and hasattr(pydyf.Stream, "set_text_matrix"):
            def _text_matrix(self, a=1, b=0, c=0, d=1, e=0, f=0):
                return self.set_text_matrix(a, b, c, d, e, f)

            pydyf.Stream.text_matrix = _text_matrix

    @classmethod
    def _render_html(cls, *, payload: dict[str, object]) -> str:
        return render_to_string(
            "webapp/letters/bk_letter_pdf.html",
            {
                "payload": payload,
                "letters_css": cls._load_letter_css(),
            },
        )

    @classmethod
    def generate_letter_pdf(cls, *, payload: dict[str, object]) -> bytes:
        html = cls._render_html(payload=payload)

        try:
            cls._patch_pydyf_compat()
            from weasyprint import HTML
        except Exception as exc:
            cls._WEASYPRINT_RUNTIME_OK = False
            raise AnnualStatementPdfGenerationError(
                "PDF-Erstellung fehlgeschlagen: WeasyPrint ist nicht verfügbar."
            ) from exc

        try:
            pdf_bytes = HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
            cls._WEASYPRINT_RUNTIME_OK = True
            return pdf_bytes
        except Exception as exc:
            cls._WEASYPRINT_RUNTIME_OK = False
            cls.logger.exception("WeasyPrint-PDF-Erzeugung fehlgeschlagen.")
            raise AnnualStatementPdfGenerationError(
                f"PDF-Erstellung fehlgeschlagen: {exc}"
            ) from exc
