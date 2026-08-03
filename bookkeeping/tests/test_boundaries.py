import ast
from pathlib import Path

from django.apps import apps
from django.test import SimpleTestCase


class BookkeepingBoundaryTests(SimpleTestCase):
    def test_models_do_not_relate_to_webapp_models(self):
        for model in apps.get_app_config("bookkeeping").get_models():
            for field in model._meta.get_fields():
                related_model = getattr(field, "related_model", None)
                self.assertFalse(
                    related_model and related_model._meta.app_label == "webapp",
                    f"{model.__name__}.{field.name} darf nicht auf webapp verweisen.",
                )

    def test_bookkeeping_python_code_does_not_import_webapp(self):
        app_root = Path(__file__).resolve().parents[1]
        for path in app_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                imported_names = []
                if isinstance(node, ast.Import):
                    imported_names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_names = [node.module]
                self.assertFalse(
                    any(name == "webapp" or name.startswith("webapp.") for name in imported_names),
                    f"Unerlaubter webapp-Import in {path}",
                )

    def test_bookkeeping_templates_and_assets_do_not_reference_webapp(self):
        app_root = Path(__file__).resolve().parents[1]
        for path in list((app_root / "templates").rglob("*")) + list((app_root / "static").rglob("*")):
            if path.is_file():
                self.assertNotIn("webapp/", path.read_text(encoding="utf-8"), f"Unerlaubte Referenz in {path}")
