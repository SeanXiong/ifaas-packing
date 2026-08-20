import sys
import unittest
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class McpServerTest(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_server_exposes_only_read_tools(self):
        root = Path(__file__).resolve().parents[1]
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(root / "ifaas_mcp.py")],
            cwd=root,
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()
        names = {tool.name for tool in result.tools}
        self.assertEqual(names, {
            "search_projects", "list_project_versions", "list_version_services",
            "inspect_release_target", "validate_release_plan",
        })
        self.assertNotIn("switch_service_branch", names)
        self.assertNotIn("create_package_task", names)


if __name__ == "__main__":
    unittest.main()
