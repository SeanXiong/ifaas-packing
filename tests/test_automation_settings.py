import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ifaas_package.automation_settings import (
    AutomationSettingsError,
    AutomationSettingsService,
    AutomationSettingsStore,
)


class FakeClient:
    def __init__(self):
        self.projects = {1: {"projectId": 1, "name": "项目一"}, 2: {"projectId": 2, "name": "项目二"}}
        self.versions = {
            1: [{"versionId": 11, "name": "产品甲", "enabled": True}],
            2: [{"versionId": 22, "name": "产品乙", "enabled": True}],
        }

    def get_project(self, project_id):
        return self.projects.get(int(project_id), {"projectId": None, "name": ""})

    def list_versions(self, project_id):
        return {"versions": self.versions.get(int(project_id), [])}

    def search_projects(self, query, page, page_size):
        matches = [item for item in self.projects.values() if query in item["name"]]
        return {"projects": matches, "page": page, "pageSize": page_size, "total": len(matches)}


class AutomationSettingsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = AutomationSettingsStore(Path(self.directory.name) / "automation-settings.json")
        self.client = FakeClient()
        self.service = AutomationSettingsService(self.store, self.client)

    def tearDown(self):
        self.directory.cleanup()

    def test_unconfigured_and_first_save(self):
        self.assertEqual(self.service.get()["status"], "UNCONFIGURED")
        result = self.service.save(1, 11, "alice")
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(result["target"]["projectName"], "项目一")
        self.assertEqual(result["audit"]["createdBy"], "alice")

    def test_update_keeps_creation_audit(self):
        first = self.store.save(
            {"projectId": 1, "projectName": "项目一", "versionId": 11, "versionName": "产品甲"},
            "alice",
            datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        result = self.service.save(2, 22, "bob")
        self.assertEqual(result["audit"]["createdBy"], "alice")
        self.assertEqual(result["audit"]["createdAt"], first["createdAt"])
        self.assertEqual(result["audit"]["updatedBy"], "bob")

    def test_rejects_unknown_and_cross_project_version(self):
        with self.assertRaisesRegex(AutomationSettingsError, "项目不存在"):
            self.service.save(99, 11, "alice")
        with self.assertRaisesRegex(AutomationSettingsError, "不属于"):
            self.service.save(1, 22, "alice")

    def test_detects_saved_target_becoming_invalid(self):
        self.service.save(1, 11, "alice")
        self.client.versions[1] = []
        result = self.service.get()
        self.assertEqual(result["status"], "INVALID")
        self.assertEqual(result["invalidReason"], "AUTOMATION_VERSION_NOT_FOUND")

    def test_candidate_search_is_normalized_and_scoped(self):
        projects = self.service.search_projects("项目", 1, 20)
        self.assertEqual(projects["total"], 2)
        versions = self.service.search_versions(1, "甲")
        self.assertEqual([item["versionId"] for item in versions["versions"]], [11])
        self.assertEqual(self.service.search_versions(1, "乙")["versions"], [])


if __name__ == "__main__":
    unittest.main()
