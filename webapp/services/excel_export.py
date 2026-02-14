from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any, Iterable, Mapping, Sequence
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from django.http import HttpResponse


@dataclass(frozen=True, slots=True)
class ExcelColumn:
    key: str
    label: str


class ExcelExportService:
    CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    @classmethod
    def build_response(
        cls,
        *,
        filename: str,
        sheet_name: str,
        columns: Sequence[ExcelColumn],
        rows: Iterable[Mapping[str, Any]],
    ) -> HttpResponse:
        workbook = cls.build_workbook(sheet_name=sheet_name, columns=columns, rows=rows)
        safe_filename = cls._sanitize_filename(filename)
        response = HttpResponse(workbook, content_type=cls.CONTENT_TYPE)
        response["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
        return response

    @classmethod
    def build_workbook(
        cls,
        *,
        sheet_name: str,
        columns: Sequence[ExcelColumn],
        rows: Iterable[Mapping[str, Any]],
    ) -> bytes:
        normalized_rows = list(rows)
        worksheet_xml = cls._build_worksheet_xml(
            sheet_name=sheet_name,
            columns=columns,
            rows=normalized_rows,
        )
        workbook_xml = cls._build_workbook_xml(sheet_name=sheet_name)

        buffer = BytesIO()
        with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", cls._content_types_xml())
            archive.writestr("_rels/.rels", cls._root_relationships_xml())
            archive.writestr("xl/workbook.xml", workbook_xml)
            archive.writestr("xl/_rels/workbook.xml.rels", cls._workbook_relationships_xml())
            archive.writestr("xl/styles.xml", cls._styles_xml())
            archive.writestr("xl/worksheets/sheet1.xml", worksheet_xml)
        return buffer.getvalue()

    @classmethod
    def _build_workbook_xml(cls, *, sheet_name: str) -> str:
        safe_name = cls._sanitize_sheet_name(sheet_name)
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>"
            f'<sheet name="{escape(safe_name)}" sheetId="1" r:id="rId2"/>'
            "</sheets>"
            "</workbook>"
        )

    @classmethod
    def _build_worksheet_xml(
        cls,
        *,
        sheet_name: str,
        columns: Sequence[ExcelColumn],
        rows: Sequence[Mapping[str, Any]],
    ) -> str:
        _ = sheet_name
        row_parts: list[str] = []
        row_parts.append(cls._build_header_row(columns=columns))
        for row_index, row in enumerate(rows, start=2):
            row_parts.append(cls._build_data_row(row_index=row_index, columns=columns, row=row))
        row_payload = "".join(row_parts)
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>"
            f"{row_payload}"
            "</sheetData>"
            "</worksheet>"
        )

    @classmethod
    def _build_header_row(cls, *, columns: Sequence[ExcelColumn]) -> str:
        cell_parts: list[str] = []
        for col_index, column in enumerate(columns, start=1):
            ref = f"{cls._column_letter(col_index)}1"
            label = escape(column.label)
            cell_parts.append(
                f'<c r="{ref}" s="1" t="inlineStr"><is><t xml:space="preserve">{label}</t></is></c>'
            )
        return f'<row r="1">{"".join(cell_parts)}</row>'

    @classmethod
    def _build_data_row(
        cls,
        *,
        row_index: int,
        columns: Sequence[ExcelColumn],
        row: Mapping[str, Any],
    ) -> str:
        cell_parts: list[str] = []
        for col_index, column in enumerate(columns, start=1):
            ref = f"{cls._column_letter(col_index)}{row_index}"
            value = row.get(column.key)
            cell_parts.append(cls._build_cell_xml(cell_ref=ref, value=value))
        return f'<row r="{row_index}">{"".join(cell_parts)}</row>'

    @classmethod
    def _build_cell_xml(cls, *, cell_ref: str, value: Any) -> str:
        if value is None:
            return f'<c r="{cell_ref}" t="inlineStr"><is><t xml:space="preserve"></t></is></c>'
        if isinstance(value, bool):
            return f'<c r="{cell_ref}"><v>{1 if value else 0}</v></c>'
        if isinstance(value, Decimal):
            return f'<c r="{cell_ref}"><v>{format(value, "f")}</v></c>'
        if isinstance(value, int):
            return f'<c r="{cell_ref}"><v>{value}</v></c>'
        if isinstance(value, float):
            return f'<c r="{cell_ref}"><v>{value}</v></c>'
        if isinstance(value, datetime):
            text = value.strftime("%Y-%m-%d %H:%M:%S")
            escaped = escape(text)
            return f'<c r="{cell_ref}" t="inlineStr"><is><t xml:space="preserve">{escaped}</t></is></c>'
        if isinstance(value, date):
            text = value.strftime("%Y-%m-%d")
            escaped = escape(text)
            return f'<c r="{cell_ref}" t="inlineStr"><is><t xml:space="preserve">{escaped}</t></is></c>'
        escaped = escape(str(value))
        return f'<c r="{cell_ref}" t="inlineStr"><is><t xml:space="preserve">{escaped}</t></is></c>'

    @staticmethod
    def _column_letter(col_number: int) -> str:
        remainder = col_number
        letters = ""
        while remainder > 0:
            remainder, offset = divmod(remainder - 1, 26)
            letters = chr(65 + offset) + letters
        return letters

    @staticmethod
    def _sanitize_sheet_name(sheet_name: str) -> str:
        cleaned = re.sub(r"[\[\]:*?/\\]", "_", (sheet_name or "").strip())
        if not cleaned:
            cleaned = "Tabelle"
        return cleaned[:31]

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", (filename or "").strip())
        if not cleaned:
            cleaned = "export.xlsx"
        if not cleaned.lower().endswith(".xlsx"):
            cleaned = f"{cleaned}.xlsx"
        return cleaned

    @staticmethod
    def _content_types_xml() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            "</Types>"
        )

    @staticmethod
    def _root_relationships_xml() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            "</Relationships>"
        )

    @staticmethod
    def _workbook_relationships_xml() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            'Target="styles.xml"/>'
            '<Relationship Id="rId2" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        )

    @staticmethod
    def _styles_xml() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2">'
            '<font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><name val="Calibri"/></font>'
            "</fonts>"
            '<fills count="2">'
            '<fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill>'
            "</fills>"
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2">'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
            "</cellXfs>"
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            "</styleSheet>"
        )
