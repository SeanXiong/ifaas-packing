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


if __name__ == "__main__":
    unittest.main()
