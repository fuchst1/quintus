from pathlib import Path
from uuid import uuid4


def kontenplan_vorlage_upload_to(_instance, filename: str) -> str:
    """Return an isolated, collision-resistant path for original workbooks."""
    suffix = Path(filename).suffix.lower() or ".xlsx"
    return f"bookkeeping/kontenplanvorlagen/{uuid4().hex}{suffix}"
