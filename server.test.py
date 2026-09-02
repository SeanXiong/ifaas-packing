import importlib.util
import pathlib
from socketserver import ThreadingMixIn
import unittest


SERVER_PATH = pathlib.Path(__file__).with_name("server.py")
SPEC = importlib.util.spec_from_file_location("ifaas_packing_server", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class LongRunningProxyPathTests(unittest.TestCase):
    def test_install_package_submission_is_a_long_running_path(self):
        self.assertIn("/api/v1/packplus/install/", SERVER.LONG_RUNNING_PROXY_PATHS)

    def test_http_server_handles_requests_in_worker_threads(self):
        self.assertTrue(issubclass(SERVER.ThreadingHTTPServer, ThreadingMixIn))
        self.assertTrue(SERVER.ThreadingHTTPServer.daemon_threads)

    def test_automation_settings_have_a_dedicated_persistence_file(self):
        self.assertEqual(SERVER.AUTOMATION_SETTINGS_PATH.name, "automation-settings.json")

    def test_automation_tasks_have_a_dedicated_persistence_file(self):
        self.assertEqual(SERVER.PACKAGE_TASKS_PATH.name, "automation-package-tasks.json")

    def test_automation_routes_do_not_reuse_credential_config(self):
        self.assertNotEqual(SERVER.AUTOMATION_SETTINGS_PATH, SERVER.SERVER_CONFIG_PATH)

    def test_automation_settings_cannot_bypass_typed_api(self):
        handler = object.__new__(SERVER.Handler)
        handler.path = "/api/config/automation-settings"
        self.assertIsNone(handler._config_name())


if __name__ == "__main__":
    unittest.main()
