import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ifaas_package.automation_settings import AutomationSettingsService, AutomationSettingsStore
from ifaas_package.client import SystemBError
from ifaas_package.package_tasks import (
    PackageTaskError,
    PackageTaskService,
    PackageTaskStore,
    PackageTaskWorker,
)


class FakeClient:
    def __init__(self):
        self.project_exists = True
        self.version_exists = True
        self.branch = "main"
        self.branches = ["main", "release/1.0"]
        self.switch_error = None

    def get_project(self, project_id):
        return {"projectId": 1, "name": "项目一"} if self.project_exists else {"projectId": None}

    def list_versions(self, project_id):
        versions = [{"versionId": 11, "name": "产品甲"}] if self.version_exists else []
        return {"versions": versions}

    def list_services(self, version_id):
        return {
            "services": [
                {
                    "serviceId": 31,
                    "name": "服务甲",
                    "gitUrl": "https://gitlab/team/service.git",
                    "branch": self.branch,
                }
            ]
        }

    def list_refs(self, git_url):
        return {"branches": self.branches, "tags": []}

    def switch_service_branch(self, version_id, service_id, branch):
        if self.switch_error:
            raise self.switch_error
        previous = self.branch
        self.branch = branch
        return {
            "changed": previous != branch,
            "previousBranch": previous,
            "currentBranch": self.branch,
        }


class RunnerClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.records = []
        self.submissions = []
        self.upload_count = 0
        self.cloud_on_submit = True
        self.cloud_on_recovery = True
        self.existing_upload_task = False
        self.progress_complete = False
        self.delay_after_submit = 0

    def list_package_records(self, package_type, version_id, offline):
        if self.submissions and self.delay_after_submit > 0:
            self.delay_after_submit -= 1
            return []
        return [dict(item) for item in self.records]

    def submit_package(self, package_type, version_id, payload):
        self.submissions.append((package_type, version_id, payload))
        self.records.append({
            "recordId": 101,
            "name": "update.tgz",
            "downloadUrl": "http://artifact/update.tgz",
            "storagePath": "/tmp/update.tgz",
            "md5": "abc",
            "cloudPath": "https://pan/update.tgz" if self.cloud_on_submit else None,
            "cloudUrl": "https://pan/update.tgz" if self.cloud_on_submit else None,
            "cloudTaskId": "combined-1" if self.existing_upload_task else None,
        })
        return {"message": "accepted"}

    def get_upload_progress(self, task_id):
        return {"complete": self.progress_complete, "success": self.progress_complete, "percent": 100 if self.progress_complete else 10}

    def upload_to_seafile(self, storage_path):
        self.upload_count += 1
        if self.cloud_on_recovery:
            self.records[0]["cloudPath"] = "https://pan/recovered.tgz"
            self.records[0]["cloudUrl"] = "https://pan/recovered.tgz"
        return {"taskId": "recovery-1"}

def valid_request(client_request_id="release-1"):
    return {
        "clientRequestId": client_request_id,
        "repositoryUrl": "git@gitlab:team/service.git",
        "branch": "release/1.0",
        "parameters": {
            "packageType": "UPGRADE",
            "networkType": "OFFLINE",
            "cpuArchitecture": "x86_64",
            "namespace": "ifaas",
            "uploadCloud": True,
        },
    }


class PackageTaskTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.client = FakeClient()
        settings_store = AutomationSettingsStore(root / "settings.json")
        settings_store.save(
            {"projectId": 1, "projectName": "项目一", "versionId": 11, "versionName": "产品甲"},
            "alice",
        )
        self.store = PackageTaskStore(root / "tasks.json")
        self.submitted = []
        self.service = PackageTaskService(
            self.store,
            AutomationSettingsService(settings_store, self.client),
            self.submitted.append,
        )

    def tearDown(self):
        self.directory.cleanup()

    def test_create_is_atomic_idempotent_and_snapshots_settings(self):
        response, created = self.service.create(valid_request())
        duplicate, duplicate_created = self.service.create(valid_request())
        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(duplicate, response)
        self.assertEqual(self.submitted, [response["packageTaskId"]])
        saved = self.store.get(response["packageTaskId"])
        self.assertEqual(saved["schemaVersion"], 1)
        self.assertEqual(saved["configurationSnapshot"]["versionName"], "产品甲")

        self.client.version_exists = False
        retry, retry_created = self.service.create(valid_request())
        self.assertFalse(retry_created)
        self.assertEqual(retry, response)

    def test_submit_happens_only_after_successful_persistence(self):
        with patch("ifaas_package.package_tasks.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(PackageTaskError) as raised:
                self.service.create(valid_request())
        self.assertEqual(raised.exception.code, "PACKAGE_TASK_PERSISTENCE_FAILED")
        self.assertEqual(self.submitted, [])

    def test_query_and_state_transitions(self):
        response, _ = self.service.create(valid_request())
        task_id = response["packageTaskId"]
        self.store.transition(task_id, "LOCATING_TARGET")
        self.store.transition(task_id, "QUEUED", {"queue": {"lockKey": "11:31", "position": 1}})
        result = self.service.get(task_id)
        self.assertEqual(result["stage"], "QUEUED")
        self.assertEqual(result["queue"]["position"], 1)
        self.assertEqual(result["parameters"]["packageType"], "UPGRADE")
        with self.assertRaisesRegex(PackageTaskError, "不能从 QUEUED"):
            self.store.transition(task_id, "SUCCESS")

    def test_recovery_resubmits_only_non_terminal_tasks(self):
        first, _ = self.service.create(valid_request("release-1"))
        second, _ = self.service.create(valid_request("release-2"))
        second_id = second["packageTaskId"]
        for stage in ("LOCATING_TARGET", "QUEUED", "ALIGNING_BRANCH", "PACKAGING_AND_UPLOADING", "VERIFYING_CLOUD_RESULT", "SUCCESS"):
            self.store.transition(second_id, stage)
        self.submitted.clear()
        self.assertEqual(self.service.recover(), [first["packageTaskId"]])
        self.assertEqual(self.submitted, [first["packageTaskId"]])

    def test_corrupted_store_returns_stable_error(self):
        self.store.path.write_text('{"schemaVersion":1,"tasks":{"bad":{}}}', encoding="utf-8")
        with self.assertRaises(PackageTaskError) as raised:
            self.store.load()
        self.assertEqual(raised.exception.code, "PACKAGE_TASK_STORE_CORRUPTED")

    def test_task_creation_detects_missing_and_invalid_configuration(self):
        missing_root = Path(self.directory.name) / "missing.json"
        missing_service = PackageTaskService(
            self.store,
            AutomationSettingsService(AutomationSettingsStore(missing_root), self.client),
        )
        with self.assertRaisesRegex(Exception, "尚未配置"):
            missing_service.create(valid_request("missing"))
        self.client.version_exists = False
        with self.assertRaisesRegex(Exception, "不属于"):
            self.service.create(valid_request("invalid"))

    def test_rejects_online_cloud_upload(self):
        request = valid_request()
        request["parameters"]["networkType"] = "ONLINE"
        with self.assertRaises(PackageTaskError) as raised:
            self.service.create(request)
        self.assertEqual(raised.exception.code, "ONLINE_CLOUD_UPLOAD_NOT_SUPPORTED")

    def test_rejects_unknown_cpu_architecture(self):
        request = valid_request()
        request["parameters"]["cpuArchitecture"] = "unknown"
        with self.assertRaises(PackageTaskError) as raised:
            self.service.create(request)
        self.assertEqual(raised.exception.code, "INVALID_CPU_ARCHITECTURE")

    def test_locates_unique_service_by_normalized_git_url(self):
        response, _ = self.service.create(valid_request())
        target = self.service.locate_target(response["packageTaskId"], self.client)
        self.assertEqual(target["serviceId"], 31)
        self.assertEqual(self.service.get(response["packageTaskId"])["target"]["serviceName"], "服务甲")

    def test_missing_and_ambiguous_service_fail_with_stable_errors(self):
        response, _ = self.service.create(valid_request("missing-service"))
        self.client.list_services = lambda _version_id: {"services": []}
        with self.assertRaises(PackageTaskError) as missing:
            self.service.locate_target(response["packageTaskId"], self.client)
        self.assertEqual(missing.exception.code, "SERVICE_NOT_FOUND")
        self.assertEqual(self.service.get(response["packageTaskId"])["stage"], "FAILED")

        response, _ = self.service.create(valid_request("ambiguous-service"))
        service = {
            "serviceId": 31,
            "name": "服务甲",
            "gitUrl": "https://gitlab/team/service.git",
        }
        self.client.list_services = lambda _version_id: {"services": [service, {**service, "serviceId": 32}]}
        with self.assertRaises(PackageTaskError) as ambiguous:
            self.service.locate_target(response["packageTaskId"], self.client)
        self.assertEqual(ambiguous.exception.code, "SERVICE_TARGET_AMBIGUOUS")

    def test_fifo_queue_hands_lock_to_only_the_next_task(self):
        task_ids = []
        for client_id in ("queue-1", "queue-2", "queue-3"):
            response, _ = self.service.create(valid_request(client_id))
            self.service.locate_target(response["packageTaskId"], self.client)
            task_ids.append(response["packageTaskId"])
        acquisitions = [self.store.enqueue(task_id, "11:31") for task_id in task_ids]
        self.assertEqual([item["acquired"] for item in acquisitions], [True, False, False])
        self.assertEqual([self.service.get(task_id)["queue"]["position"] for task_id in task_ids], [0, 1, 2])
        self.assertEqual(self.store.release(task_ids[0], "11:31"), task_ids[1])
        self.assertEqual(self.service.get(task_ids[1])["queue"]["position"], 0)
        with self.assertRaises(PackageTaskError):
            self.store.release(task_ids[2], "11:31")

    def test_different_lock_keys_can_be_owned_and_orphan_lock_is_repaired(self):
        owners = []
        for index, lock_key in enumerate(("11:31", "11:32"), 1):
            response, _ = self.service.create(valid_request(f"parallel-{index}"))
            self.service.locate_target(response["packageTaskId"], self.client)
            self.assertTrue(self.store.enqueue(response["packageTaskId"], lock_key)["acquired"])
            owners.append(response["packageTaskId"])
        database = self.store.load()
        database["locks"]["orphan"] = "missing-task"
        self.store._write_unlocked(database)
        self.assertCountEqual(self.store.repair_queues(), owners)
        self.assertNotIn("orphan", self.store.load()["locks"])

    def _create_owned_task(self, client_id):
        response, _ = self.service.create(valid_request(client_id))
        task_id = response["packageTaskId"]
        target = self.service.locate_target(task_id, self.client)
        self.store.enqueue(task_id, f"{target['versionId']}:{target['serviceId']}")
        return task_id

    def test_branch_alignment_skips_matching_branch_and_records_result(self):
        self.client.branch = "release/1.0"
        task_id = self._create_owned_task("aligned")
        result = self.service.align_branch(task_id, self.client)
        self.assertFalse(result["changed"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["previousBranch"], "release/1.0")

    def test_branch_alignment_switches_and_does_not_restore(self):
        task_id = self._create_owned_task("switch")
        result = self.service.align_branch(task_id, self.client)
        self.assertTrue(result["changed"])
        self.assertEqual(result["previousBranch"], "main")
        self.assertEqual(self.client.branch, "release/1.0")

    def test_branch_alignment_fails_for_missing_branch_and_update_error(self):
        task_id = self._create_owned_task("missing-branch")
        self.client.branches = ["main"]
        with self.assertRaises(PackageTaskError) as missing:
            self.service.align_branch(task_id, self.client)
        self.assertEqual(missing.exception.code, "BRANCH_ALIGNMENT_FAILED")
        self.assertEqual(self.client.branch, "main")

        self.client.branches = ["main", "release/1.0"]
        self.client.switch_error = SystemBError("GIT_CONFIG_NOT_FOUND", "目标分支缺少 git_id")
        task_id = self._create_owned_task("update-error")
        with self.assertRaises(PackageTaskError):
            self.service.align_branch(task_id, self.client)
        error = self.service.get(task_id)["error"]
        self.assertEqual(error["details"]["reasonCode"], "GIT_CONFIG_NOT_FOUND")

    def test_branch_alignment_detects_verification_failure(self):
        task_id = self._create_owned_task("verify-error")
        self.client.switch_service_branch = lambda *_args: {
            "changed": True,
            "previousBranch": "main",
            "currentBranch": "main",
        }
        with self.assertRaises(PackageTaskError):
            self.service.align_branch(task_id, self.client)
        error = self.service.get(task_id)["error"]
        self.assertEqual(error["details"]["reasonCode"], "BRANCH_UPDATE_NOT_APPLIED")

    def test_recovery_schedules_only_fifo_lock_owners(self):
        task_ids = []
        for client_id in ("recover-owner", "recover-waiter"):
            response, _ = self.service.create(valid_request(client_id))
            task_id = response["packageTaskId"]
            self.service.locate_target(task_id, self.client)
            self.store.enqueue(task_id, "11:31")
            task_ids.append(task_id)
        self.submitted.clear()
        self.assertEqual(self.service.recover(), [task_ids[0]])
        self.assertEqual(self.submitted, [task_ids[0]])


class PackageTaskWorkerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.client = RunnerClient()
        settings_store = AutomationSettingsStore(root / "settings.json")
        settings_store.save(
            {"projectId": 1, "projectName": "项目一", "versionId": 11, "versionName": "产品甲"},
            "alice",
        )
        self.store = PackageTaskStore(root / "tasks.json")
        self.scheduled = []
        self.service = PackageTaskService(
            self.store,
            AutomationSettingsService(settings_store, self.client),
            self.scheduled.append,
        )

    def tearDown(self):
        self.directory.cleanup()

    def _run(self, request=None, attempts=3):
        response, _ = self.service.create(request or valid_request())
        task_id = response["packageTaskId"]
        PackageTaskWorker(
            self.service,
            self.client,
            poll_attempts=attempts,
            poll_interval=0,
            sleeper=lambda _seconds: None,
        ).run(task_id)
        return self.service.get(task_id)

    def test_combined_package_upload_succeeds_without_second_upload(self):
        result = self._run()
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["artifact"]["cloudUrl"], "https://pan/update.tgz")
        self.assertEqual(self.client.upload_count, 0)
        payload = self.client.submissions[0][2]
        self.assertTrue(payload["seafile"])
        self.assertEqual(payload["modules"][0]["pk"], 31)

    def test_delayed_record_and_no_cloud_request_succeed(self):
        self.client.cloud_on_submit = False
        self.client.delay_after_submit = 1
        request = valid_request("no-cloud")
        request["parameters"]["uploadCloud"] = False
        result = self._run(request)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertIsNone(result["artifact"]["cloudUrl"])

    def test_existing_upload_is_waited_without_compensation(self):
        self.client.cloud_on_submit = False
        self.client.existing_upload_task = True
        result = self._run(valid_request("existing-upload"), attempts=2)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error"]["code"], "CLOUD_UPLOAD_TIMEOUT")
        self.assertEqual(self.client.upload_count, 0)

    def test_missing_cloud_address_triggers_one_recovery(self):
        self.client.cloud_on_submit = False
        result = self._run(valid_request("recovery"))
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["artifact"]["cloudRecoveryTriggered"], True)
        self.assertEqual(self.client.upload_count, 1)

    def test_failed_recovery_is_not_repeated(self):
        self.client.cloud_on_submit = False
        self.client.cloud_on_recovery = False
        result = self._run(valid_request("recovery-failed"), attempts=2)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["error"]["code"], "CLOUD_ADDRESS_MISSING")
        task_id = result["packageTaskId"]
        PackageTaskWorker(self.service, self.client, 2, 0, lambda _seconds: None).run(task_id)
        self.assertEqual(self.client.upload_count, 1)

    def test_restart_after_package_request_only_queries_existing_record(self):
        response, _ = self.service.create(valid_request("package-restart"))
        task_id = response["packageTaskId"]
        target = self.service.locate_target(task_id, self.client)
        self.store.enqueue(task_id, f"{target['versionId']}:{target['serviceId']}")
        self.service.align_branch(task_id, self.client)
        self.store.transition(
            task_id,
            "PACKAGING_AND_UPLOADING",
            {
                "execution": {
                    "baselineRecordIds": [],
                    "packageRequestStarted": True,
                    "packageResponseReceived": False,
                }
            },
        )
        self.client.records.append({
            "recordId": 102,
            "name": "restart.tgz",
            "downloadUrl": "http://artifact/restart.tgz",
            "storagePath": "/tmp/restart.tgz",
            "md5": "def",
            "cloudPath": "https://pan/restart.tgz",
            "cloudUrl": "https://pan/restart.tgz",
            "cloudTaskId": None,
        })
        PackageTaskWorker(self.service, self.client, 2, 0, lambda _seconds: None).run(task_id)
        self.assertEqual(self.service.get(task_id)["status"], "SUCCESS")
        self.assertEqual(self.client.submissions, [])

    def test_restart_during_cloud_recovery_does_not_upload_again(self):
        response, _ = self.service.create(valid_request("cloud-restart"))
        task_id = response["packageTaskId"]
        target = self.service.locate_target(task_id, self.client)
        self.store.enqueue(task_id, f"{target['versionId']}:{target['serviceId']}")
        self.service.align_branch(task_id, self.client)
        self.store.transition(task_id, "PACKAGING_AND_UPLOADING")
        self.store.transition(
            task_id,
            "VERIFYING_CLOUD_RESULT",
            {
                "artifact": {
                    "name": "update.tgz",
                    "downloadUrl": "http://artifact/update.tgz",
                    "md5": "abc",
                    "cloudPath": None,
                    "cloudUrl": None,
                    "cloudRecoveryTriggered": False,
                }
            },
        )
        self.store.release(task_id, f"{target['versionId']}:{target['serviceId']}")
        self.store.transition(
            task_id,
            "RECOVERING_CLOUD_UPLOAD",
            {
                "execution": {
                    "recordId": "101",
                    "storagePath": "/tmp/update.tgz",
                    "cloudRecoveryStarted": True,
                    "cloudRecoveryTaskId": "recovery-1",
                }
            },
        )
        self.client.cloud_on_recovery = False
        self.client.records.append({
            "recordId": 101,
            "name": "update.tgz",
            "downloadUrl": "http://artifact/update.tgz",
            "storagePath": "/tmp/update.tgz",
            "md5": "abc",
            "cloudPath": None,
            "cloudUrl": None,
            "cloudTaskId": None,
        })
        PackageTaskWorker(self.service, self.client, 2, 0, lambda _seconds: None).run(task_id)
        self.assertEqual(self.service.get(task_id)["error"]["code"], "CLOUD_ADDRESS_MISSING")
        self.assertEqual(self.client.upload_count, 0)


if __name__ == "__main__":
    unittest.main()
