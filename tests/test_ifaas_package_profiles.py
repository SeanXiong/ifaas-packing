import json
import unittest

from ifaas_package.client import SystemBError
from ifaas_package.profiles import PackingProfileClientPool


class ProfileTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        payload = json.loads(body.decode("utf-8")) if body else None
        self.calls.append((method, url, headers, payload, timeout))
        if url.endswith("/api/config/login-profiles"):
            return 200, {
                "accounts": {
                    "alice": {"username": "alice", "password": "alice-secret"},
                    "bob": {"username": "bob", "password": "bob-secret"},
                }
            }
        if url.endswith("/api/proxy/rest-auth/login/"):
            return 200, {"key": f"token-{payload['username']}"}
        if "/api/proxy/api/v1/project/?" in url:
            return 200, {"results": [{"id": 1, "name": "项目一"}], "count": 1}
        return 404, {"message": "not found"}


class PackingProfileClientPoolTest(unittest.TestCase):
    def setUp(self):
        self.transport = ProfileTransport()
        self.pool = PackingProfileClientPool("http://packing.example", self.transport)

    def test_profiles_only_expose_usernames(self):
        result = self.pool.list_profiles()
        self.assertEqual(result, {"accounts": [{"username": "alice"}, {"username": "bob"}]})
        self.assertNotIn("secret", json.dumps(result))

    def test_selected_profile_logs_in_through_proxy_and_reuses_token(self):
        result = self.pool.authenticate("alice")
        self.assertEqual(result, {"authenticated": True, "username": "alice"})
        projects = self.pool.client_for("alice").search_projects("项目")
        self.assertEqual(projects["projects"][0]["projectId"], 1)
        login_calls = [call for call in self.transport.calls if call[1].endswith("/rest-auth/login/")]
        self.assertEqual(len(login_calls), 1)
        project_call = next(call for call in self.transport.calls if "/project/?" in call[1])
        self.assertEqual(project_call[2]["Authorization"], "Token token-alice")

    def test_unknown_profile_is_rejected_before_login(self):
        with self.assertRaises(SystemBError) as raised:
            self.pool.authenticate("unknown")
        self.assertEqual(raised.exception.code, "LOGIN_PROFILE_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
