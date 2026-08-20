import argparse
import unittest

from ifaas_package.cli import execute


class StubClient:
    def search_projects(self, query, page, page_size):
        return {"query": query, "page": page, "pageSize": page_size}

    def switch_service_branch(self, version_id, service_id, branch):
        return {"versionId": version_id, "serviceId": service_id, "branch": branch}


class CliTest(unittest.TestCase):
    def test_search_command(self):
        args = argparse.Namespace(group="projects", command="search", query="工具", page=2, page_size=10)
        self.assertEqual(execute(args, StubClient()), {"query": "工具", "page": 2, "pageSize": 10})

    def test_switch_branch_command(self):
        args = argparse.Namespace(group="services", command="switch-branch", version_id="2", service_id="3", branch="main")
        self.assertEqual(execute(args, StubClient())["branch"], "main")


if __name__ == "__main__":
    unittest.main()
