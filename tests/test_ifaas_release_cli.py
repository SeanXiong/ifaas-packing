import argparse
import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".agents/plugins/plugins/ifaas-release/skills/ifaas-release/scripts/ifaas_release.py"
)
SPEC = importlib.util.spec_from_file_location("ifaas_release_cli", SCRIPT)
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


def arguments(**changes):
    values = {
        "repository": ".",
        "remote": "origin",
        "gitlab_project_id": "123",
        "package_type": "UPGRADE",
        "network_type": "OFFLINE",
        "cpu_architecture": "x86_64",
        "namespace": "ifaas",
        "upload_cloud": True,
    }
    values.update(changes)
    return argparse.Namespace(**values)


class IfaasReleaseCliTests(unittest.TestCase):
    def test_build_request_reads_and_normalizes_git_context(self):
        outputs = ["git@gitlab.example.com:Team/Service.git", "release/1.0", "a" * 40]
        with patch.object(CLI, "git_output", side_effect=outputs):
            request = CLI.build_request(arguments())
        self.assertEqual(request["repositoryUrl"], "https://gitlab.example.com/team/service.git")
        self.assertEqual(request["branch"], "release/1.0")
        self.assertEqual(request["commitSha"], "a" * 40)
        self.assertTrue(request["clientRequestId"].startswith("codex-"))

    def test_same_release_intent_has_stable_client_request_id(self):
        outputs = ["https://gitlab/Team/Service.git", "main", "b" * 40]
        with patch.object(CLI, "git_output", side_effect=outputs * 2):
            first = CLI.build_request(arguments())
            second = CLI.build_request(arguments())
        self.assertEqual(first["clientRequestId"], second["clientRequestId"])

    def test_register_reads_configuration_from_environment(self):
        environment = {
            "IFAAS_BUILD_PLATFORM_URL": "http://127.0.0.1:8765/",
            "IFAAS_BUILD_PLATFORM_TOKEN": "secret",
        }
        with patch.dict(os.environ, environment, clear=True), patch.object(
            CLI,
            "request_json",
            return_value={"releaseTaskId": "rel-1", "status": "READY_TO_PUSH"},
        ) as request_json:
            result = CLI.register({"clientRequestId": "request-1"})
        self.assertEqual(result, {"releaseTaskId": "rel-1", "status": "READY_TO_PUSH"})
        self.assertEqual(request_json.call_args.args[1], "http://127.0.0.1:8765/api/release-tasks")
        self.assertEqual(request_json.call_args.args[2], "secret")

    def test_registration_failure_prevents_push(self):
        with patch.object(CLI, "git_output", return_value=""), patch.object(
            CLI, "register", side_effect=CLI.ReleaseError("登记失败")
        ), patch.object(CLI.subprocess, "run") as run:
            with self.assertRaises(CLI.ReleaseError):
                CLI.release(arguments(), {"branch": "main"})
        run.assert_not_called()

    def test_push_failure_is_reported(self):
        failed = argparse.Namespace(returncode=1)
        environment = {
            "IFAAS_BUILD_PLATFORM_URL": "http://127.0.0.1:8765",
            "IFAAS_BUILD_PLATFORM_TOKEN": "secret",
        }
        with patch.dict(os.environ, environment, clear=True), patch.object(
            CLI, "git_output", return_value=""
        ), patch.object(
            CLI, "register", return_value={"releaseTaskId": "rel-1", "status": "READY_TO_PUSH"}
        ), patch.object(CLI.subprocess, "run", return_value=failed), patch.object(
            CLI, "request_json", return_value={}
        ) as request_json:
            with self.assertRaises(CLI.ReleaseError):
                CLI.release(arguments(), {"branch": "main"})
        self.assertTrue(request_json.call_args.args[1].endswith("/api/release-tasks/rel-1/push-failed"))
        self.assertEqual(request_json.call_args.args[3]["code"], "PUSH_FAILED")

    def test_online_cloud_upload_is_rejected(self):
        outputs = ["https://gitlab/team/service.git", "main", "c" * 40]
        with patch.object(CLI, "git_output", side_effect=outputs):
            with self.assertRaises(CLI.ReleaseError):
                CLI.build_request(arguments(network_type="ONLINE"))


if __name__ == "__main__":
    unittest.main()
