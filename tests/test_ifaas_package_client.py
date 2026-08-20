import json
import unittest

from ifaas_package.client import SystemBClient, SystemBError, normalize_git_url
from ifaas_package.config import SystemBConfig


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.expire_next_project_request = False

    def __call__(self, method, url, headers, body, timeout):
        payload = json.loads(body.decode("utf-8")) if body else None
        self.calls.append((method, url, headers, payload, timeout))
        if url.endswith("/rest-auth/login/"):
            return 200, {"key": "secret-token"}
        if "/api/v1/project/?" in url:
            if self.expire_next_project_request:
                self.expire_next_project_request = False
                return 401, {"message": "token expired"}
            return 200, {"page": 1, "pageSize": 20, "count": 1, "results": [{"id": 594, "name": "外部工具", "creator": {"password": "hash"}}]}
        if url.endswith("/api/v1/project/594"):
            return 200, {"id": 594, "name": "外部工具", "creator": {"password": "hash"}}
        if "/api/v1/version/?" in url:
            return 200, [{"id": 2451, "update_version": "2.0.3"}]
        if "/api/v1/module/?" in url:
            branch = "rel_2.0.3" if any(call[1].endswith("/api/v1/module/3001") for call in self.calls) else "rel_2.0.2"
            return 200, [{
                "id": 3001,
                "name": "ifaas-service",
                "custom_name": "ifaas-service",
                "branch": branch,
                "service_type": 1,
                "version": 2451,
                "git_url": {"id": 944386, "git_url": "http://gitlab/chengdu/ifaas-service.git"},
            }]
        if url.endswith("/api/v1/refs/"):
            return 200, {"data": {"branches": ["rel_2.0.2", "rel_2.0.3"], "tags": []}}
        if url.endswith("/api/v1/git_config/"):
            return 200, {"data": {"git_id": 944387}}
        if url.endswith("/api/v1/module/3001"):
            return 200, {"resultCode": 0}
        if url.endswith("/api/v1/automation/package-tasks"):
            return 202, {"taskId": "pkg-1", "status": "CREATED"}
        if url.endswith("/api/v1/automation/package-tasks/pkg-1"):
            return 200, {"taskId": "pkg-1", "status": "SUCCESS", "artifact": {"name": "a.tgz", "cloudUrl": "https://pan/a", "md5": "abc", "internal": "secret"}}
        return 404, {"message": "not found"}


class SystemBClientTest(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.client = SystemBClient(SystemBConfig("http://system-b", "user", "password"), self.transport)

    def test_query_results_use_allowlisted_fields(self):
        result = self.client.search_projects("外部")
        self.assertEqual(result["projects"], [{"projectId": 594, "name": "外部工具", "description": ""}])
        self.assertNotIn("password", json.dumps(result))

    def test_expired_token_reauthenticates_once(self):
        self.transport.expire_next_project_request = True
        result = self.client.search_projects("外部")
        self.assertEqual(result["total"], 1)
        login_calls = [call for call in self.transport.calls if call[1].endswith("/rest-auth/login/")]
        self.assertEqual(len(login_calls), 2)

    def test_inspect_matches_ssh_and_http_repository(self):
        result = self.client.inspect_release_target(2451, "git@gitlab:chengdu/ifaas-service.git", "rel_2.0.3")
        self.assertTrue(result["canPackage"])
        self.assertTrue(result["serviceMatches"][0]["requiresBranchChange"])

    def test_switch_branch_uses_git_config_and_verifies(self):
        result = self.client.switch_service_branch(2451, 3001, "rel_2.0.3")
        self.assertTrue(result["changed"])
        update = next(call for call in self.transport.calls if call[0] == "PUT")
        self.assertEqual(update[3]["git_url"], 944387)
        self.assertEqual(update[3]["branch"], "rel_2.0.3")

    def test_automation_task_contract(self):
        created = self.client.create_package_task({"clientRequestId": "release-1"})
        self.assertEqual(created["taskId"], "pkg-1")
        task = self.client.get_package_task("pkg-1")
        self.assertEqual(task["artifact"]["cloudUrl"], "https://pan/a")
        self.assertNotIn("internal", json.dumps(task))

    def test_missing_credentials_is_stable_error(self):
        client = SystemBClient(SystemBConfig("http://system-b"), self.transport)
        with self.assertRaises(SystemBError) as raised:
            client.search_projects()
        self.assertEqual(raised.exception.code, "AUTH_CONFIGURATION_MISSING")

    def test_normalize_git_url(self):
        self.assertEqual(
            normalize_git_url("https://GITLAB/chengdu/ifaas-service.git"),
            normalize_git_url("git@gitlab:chengdu/ifaas-service.git"),
        )


if __name__ == "__main__":
    unittest.main()
