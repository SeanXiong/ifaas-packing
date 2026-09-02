import ast
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON36_RUNTIME_FILES = [
    ROOT / "server.py",
    ROOT / "ifaas_pack.py",
    ROOT / "ifaas_package" / "__init__.py",
    ROOT / "ifaas_package" / "config.py",
    ROOT / "ifaas_package" / "client.py",
    ROOT / "ifaas_package" / "automation_settings.py",
    ROOT / "ifaas_package" / "package_tasks.py",
    ROOT / "ifaas_package" / "cli.py",
    ROOT / "ifaas_package" / "profiles.py",
]


class Python36CompatibilityTests(unittest.TestCase):
    def test_primary_runtime_files_parse_as_python36(self):
        for path in PYTHON36_RUNTIME_FILES:
            source = path.read_text(encoding="utf-8")
            if sys.version_info >= (3, 8):
                ast.parse(source, filename=str(path), feature_version=(3, 6))
            else:
                compile(source, str(path), "exec")

    def test_primary_runtime_avoids_unavailable_standard_library_features(self):
        for path in PYTHON36_RUNTIME_FILES:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    imported = {item.name for item in node.names}
                    self.assertFalse(
                        node.module == "__future__" and "annotations" in imported,
                        str(path),
                    )
                    self.assertNotEqual(node.module, "dataclasses", str(path))
                    self.assertFalse(
                        node.module == "typing" and "Protocol" in imported,
                        str(path),
                    )
                if isinstance(node, ast.Call):
                    keywords = {item.arg for item in node.keywords}
                    self.assertNotIn("cancel_futures", keywords, str(path))
                    if isinstance(node.func, ast.Attribute) and node.func.attr == "add_subparsers":
                        self.assertNotIn("required", keywords, str(path))


if __name__ == "__main__":
    unittest.main()
