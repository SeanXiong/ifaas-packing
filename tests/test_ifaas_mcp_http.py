import os
import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

from ifaas_package.mcp_http import create_http_app


class McpHttpTest(unittest.TestCase):
    def test_access_token_is_required_at_startup(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                create_http_app()

    def test_health_is_public_but_mcp_requires_bearer_token(self):
        with patch.dict(os.environ, {"IFAAS_MCP_ACCESS_TOKEN": "access-secret"}, clear=True):
            with TestClient(create_http_app()) as client:
                self.assertEqual(client.get("/health").status_code, 200)
                response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
                self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
