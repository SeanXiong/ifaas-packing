"""自动打包任务的持久化、状态迁移与幂等服务。"""

import copy
import json
import os
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .automation_settings import AutomationSettingsError, AutomationSettingsService
from .client import SystemBError, normalize_git_url


SCHEMA_VERSION = 1
TERMINAL_STAGES = {"SUCCESS", "FAILED"}
STAGE_PROGRESS = {
    "ACCEPTED": 0,
    "LOCATING_TARGET": 5,
    "QUEUED": 15,
    "ALIGNING_BRANCH": 25,
    "PACKAGING_AND_UPLOADING": 40,
    "VERIFYING_CLOUD_RESULT": 80,
    "RECOVERING_CLOUD_UPLOAD": 85,
    "SUCCESS": 100,
    "FAILED": 100,
}
ALLOWED_TRANSITIONS = {
    "ACCEPTED": {"LOCATING_TARGET", "FAILED"},
    "LOCATING_TARGET": {"QUEUED", "FAILED"},
    "QUEUED": {"ALIGNING_BRANCH", "FAILED"},
    "ALIGNING_BRANCH": {"PACKAGING_AND_UPLOADING", "FAILED"},
    "PACKAGING_AND_UPLOADING": {"VERIFYING_CLOUD_RESULT", "FAILED"},
    "VERIFYING_CLOUD_RESULT": {"RECOVERING_CLOUD_UPLOAD", "SUCCESS", "FAILED"},
    "RECOVERING_CLOUD_UPLOAD": {"SUCCESS", "FAILED"},
    "SUCCESS": set(),
    "FAILED": set(),
}


class PackageTaskError(RuntimeError):
    def __init__(self, code, message, status=400):
        RuntimeError.__init__(self, message)
        self.code = code
        self.message = message
        self.status = status

    def __str__(self) -> str:
        return self.message


class PackageTaskStore:
    """以单文件原子保存任务和幂等索引。"""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()

    def load(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._load_unlocked())

    def create(
        self, request: dict, target: dict, now: "datetime | None" = None
    ) -> "tuple[dict, bool]":
        with self._lock:
            database = self._load_unlocked()
            client_request_id = request["clientRequestId"]
            existing_id = database["clientRequestIndex"].get(client_request_id)
            if existing_id:
                return copy.deepcopy(database["tasks"][existing_id]), False

            timestamp = _timestamp(now)
            task_id = f"pkg-{uuid.uuid4()}"
            task = {
                "schemaVersion": SCHEMA_VERSION,
                "packageTaskId": task_id,
                "clientRequestId": client_request_id,
                "requestSnapshot": copy.deepcopy(request),
                "configurationSnapshot": copy.deepcopy(target),
                "status": "ACCEPTED",
                "stage": "ACCEPTED",
                "progress": STAGE_PROGRESS["ACCEPTED"],
                "target": None,
                "queue": None,
                "branchAlignment": None,
                "artifact": None,
                "error": None,
                "createdAt": timestamp,
                "updatedAt": timestamp,
            }
            database["tasks"][task_id] = task
            database["clientRequestIndex"][client_request_id] = task_id
            self._write_unlocked(database)
            return copy.deepcopy(task), True

    def get(self, task_id: str) -> "dict | None":
        with self._lock:
            task = self._load_unlocked()["tasks"].get(task_id)
            return copy.deepcopy(task) if task else None

    def get_by_client_request_id(self, client_request_id: str) -> "dict | None":
        with self._lock:
            database = self._load_unlocked()
            task_id = database["clientRequestIndex"].get(client_request_id)
            task = database["tasks"].get(task_id) if task_id else None
            return copy.deepcopy(task) if task else None

    def transition(self, task_id: str, stage: str, changes: "dict | None" = None) -> dict:
        with self._lock:
            database = self._load_unlocked()
            task = database["tasks"].get(task_id)
            if task is None:
                raise PackageTaskError("PACKAGE_TASK_NOT_FOUND", "自动打包任务不存在。", 404)
            current = task["stage"]
            if stage != current and stage not in ALLOWED_TRANSITIONS[current]:
                raise PackageTaskError(
                    "INVALID_PACKAGE_TASK_TRANSITION",
                    f"自动打包任务不能从 {current} 迁移到 {stage}。",
                    409,
                )
            task.update(copy.deepcopy(changes or {}))
            task["stage"] = stage
            task["status"] = "SUCCESS" if stage == "SUCCESS" else "FAILED" if stage == "FAILED" else "RUNNING"
            task["progress"] = STAGE_PROGRESS[stage]
            task["updatedAt"] = _timestamp()
            self._validate_task(task, task_id)
            self._write_unlocked(database)
            return copy.deepcopy(task)

    def enqueue(self, task_id: str, lock_key: str) -> dict:
        """把已定位任务加入持久化 FIFO，并为队首分配独占锁。"""

        with self._lock:
            database = self._load_unlocked()
            task = database["tasks"].get(task_id)
            if task is None:
                raise PackageTaskError("PACKAGE_TASK_NOT_FOUND", "自动打包任务不存在。", 404)
            if task["stage"] not in {"LOCATING_TARGET", "QUEUED"} or not task.get("target"):
                raise PackageTaskError("PACKAGE_TASK_STAGE_CONFLICT", "当前任务不能进入服务队列。", 409)
            queue = database["queues"].setdefault(lock_key, [])
            if task_id not in queue:
                queue.append(task_id)
            owner = database["locks"].get(lock_key)
            if owner not in queue:
                database["locks"][lock_key] = queue[0]
            self._refresh_queue_unlocked(database, lock_key)
            self._write_unlocked(database)
            return {
                "acquired": database["locks"][lock_key] == task_id,
                "position": queue.index(task_id),
                "lockKey": lock_key,
            }

    def release(self, task_id: str, lock_key: str) -> "str | None":
        """释放当前所有者，只把锁交给同键 FIFO 的下一个任务。"""

        with self._lock:
            database = self._load_unlocked()
            if database["locks"].get(lock_key) != task_id:
                raise PackageTaskError("PACKAGE_TASK_LOCK_NOT_OWNED", "当前任务不是服务锁所有者。", 409)
            queue = database["queues"].get(lock_key, [])
            database["queues"][lock_key] = [item for item in queue if item != task_id]
            remaining = database["queues"][lock_key]
            if remaining:
                database["locks"][lock_key] = remaining[0]
                self._refresh_queue_unlocked(database, lock_key)
                next_task_id = remaining[0]
            else:
                database["queues"].pop(lock_key, None)
                database["locks"].pop(lock_key, None)
                next_task_id = None
            self._write_unlocked(database)
            return next_task_id

    def repair_queues(self) -> "list[str]":
        """移除终态/缺失任务和孤儿锁，并恢复每个队列唯一所有者。"""

        with self._lock:
            database = self._load_unlocked()
            for lock_key, queue in list(database["queues"].items()):
                valid = [
                    task_id
                    for task_id in queue
                    if task_id in database["tasks"]
                    and database["tasks"][task_id]["stage"] not in TERMINAL_STAGES
                ]
                if not valid:
                    database["queues"].pop(lock_key, None)
                    database["locks"].pop(lock_key, None)
                    continue
                database["queues"][lock_key] = valid
                database["locks"][lock_key] = valid[0]
                self._refresh_queue_unlocked(database, lock_key)
            for lock_key in list(database["locks"]):
                if lock_key not in database["queues"]:
                    database["locks"].pop(lock_key, None)
            self._write_unlocked(database)
            return list(database["locks"].values())

    def owns_lock(self, task_id: str, lock_key: str) -> bool:
        with self._lock:
            return self._load_unlocked()["locks"].get(lock_key) == task_id

    def non_terminal(self) -> "list[dict]":
        with self._lock:
            tasks = self._load_unlocked()["tasks"].values()
            return [copy.deepcopy(task) for task in tasks if task["stage"] not in TERMINAL_STAGES]

    def _load_unlocked(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {
                "schemaVersion": SCHEMA_VERSION,
                "tasks": {},
                "clientRequestIndex": {},
                "queues": {},
                "locks": {},
            }
        except (OSError, json.JSONDecodeError) as error:
            raise PackageTaskError(
                "PACKAGE_TASK_STORE_CORRUPTED", "自动打包任务存储无法读取。", 500
            ) from error
        if not isinstance(data, dict) or data.get("schemaVersion") != SCHEMA_VERSION:
            raise PackageTaskError("PACKAGE_TASK_STORE_CORRUPTED", "自动打包任务存储版本无效。", 500)
        tasks = data.get("tasks")
        index = data.get("clientRequestIndex")
        data.setdefault("queues", {})
        data.setdefault("locks", {})
        if not isinstance(tasks, dict) or not isinstance(index, dict):
            raise PackageTaskError("PACKAGE_TASK_STORE_CORRUPTED", "自动打包任务存储结构无效。", 500)
        if not isinstance(data["queues"], dict) or not isinstance(data["locks"], dict):
            raise PackageTaskError("PACKAGE_TASK_STORE_CORRUPTED", "自动打包任务队列结构无效。", 500)
        for task_id, task in tasks.items():
            self._validate_task(task, task_id)
        for client_request_id, task_id in index.items():
            if not isinstance(client_request_id, str) or task_id not in tasks:
                raise PackageTaskError("PACKAGE_TASK_STORE_CORRUPTED", "自动打包任务索引无效。", 500)
        return data

    @staticmethod
    def _refresh_queue_unlocked(database: dict, lock_key: str) -> None:
        queue = database["queues"].get(lock_key, [])
        timestamp = _timestamp()
        for position, task_id in enumerate(queue):
            task = database["tasks"][task_id]
            waiting_since = (task.get("queue") or {}).get("waitingSince") or timestamp
            if task["stage"] in {"LOCATING_TARGET", "QUEUED"}:
                task["stage"] = "QUEUED"
                task["status"] = "RUNNING"
                task["progress"] = STAGE_PROGRESS["QUEUED"]
            task["queue"] = {
                "lockKey": lock_key,
                "position": position,
                "waitingSince": None if position == 0 else waiting_since,
            }
            task["updatedAt"] = timestamp

    @staticmethod
    def _validate_task(task: object, task_id: str) -> None:
        if not isinstance(task, dict):
            raise PackageTaskError("PACKAGE_TASK_STORE_CORRUPTED", "自动打包任务记录无效。", 500)
        if task.get("schemaVersion") != SCHEMA_VERSION or task.get("packageTaskId") != task_id:
            raise PackageTaskError("PACKAGE_TASK_STORE_CORRUPTED", "自动打包任务记录版本或 ID 无效。", 500)
        if task.get("stage") not in ALLOWED_TRANSITIONS:
            raise PackageTaskError("PACKAGE_TASK_STORE_CORRUPTED", "自动打包任务阶段无效。", 500)
        if not isinstance(task.get("requestSnapshot"), dict) or not isinstance(task.get("configurationSnapshot"), dict):
            raise PackageTaskError("PACKAGE_TASK_STORE_CORRUPTED", "自动打包任务快照无效。", 500)

    def _write_unlocked(self, database: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(database, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, self.path)
        except (OSError, TypeError, ValueError) as error:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise PackageTaskError(
                "PACKAGE_TASK_PERSISTENCE_FAILED",
                "自动打包任务无法持久化。",
                500,
            ) from error


class PackageTaskService:
    """校验创建请求，并在持久化成功后调度自动任务。"""

    def __init__(
        self,
        store: PackageTaskStore,
        settings: AutomationSettingsService,
        submit: "Callable[[str], None] | None" = None,
    ):
        self.store = store
        self.settings = settings
        self.submit = submit

    def create(self, payload: object) -> "tuple[dict, bool]":
        request = _validated_request(payload)
        existing = self.store.get_by_client_request_id(request["clientRequestId"])
        if existing is not None:
            return {"packageTaskId": existing["packageTaskId"], "status": "ACCEPTED"}, False
        target = self.settings.require_valid_target()
        task, created = self.store.create(request, target)
        if created and self.submit is not None:
            self.submit(task["packageTaskId"])
        return {
            "packageTaskId": task["packageTaskId"],
            "status": "ACCEPTED",
        }, created

    def get(self, task_id: str) -> dict:
        task = self.store.get(task_id)
        if task is None:
            raise PackageTaskError("PACKAGE_TASK_NOT_FOUND", "自动打包任务不存在。", 404)
        request = task["requestSnapshot"]
        return {
            "schemaVersion": task["schemaVersion"],
            "packageTaskId": task["packageTaskId"],
            "clientRequestId": task["clientRequestId"],
            "status": task["status"],
            "stage": task["stage"],
            "progress": task["progress"],
            "parameters": copy.deepcopy(request["parameters"]),
            "target": copy.deepcopy(task["target"]),
            "queue": copy.deepcopy(task["queue"]),
            "branchAlignment": copy.deepcopy(task["branchAlignment"]),
            "artifact": copy.deepcopy(task["artifact"]),
            "error": copy.deepcopy(task["error"]),
            "createdAt": task["createdAt"],
            "updatedAt": task["updatedAt"],
        }

    def recover(self) -> "list[str]":
        owners = set(self.store.repair_queues())
        task_ids = []
        for task in self.store.non_terminal():
            queue = task.get("queue") or {}
            if (
                task["stage"] in {"QUEUED", "ALIGNING_BRANCH", "PACKAGING_AND_UPLOADING"}
                and queue.get("lockKey")
                and task["packageTaskId"] not in owners
            ):
                continue
            task_ids.append(task["packageTaskId"])
        if self.submit is not None:
            for task_id in task_ids:
                self.submit(task_id)
        return task_ids

    def locate_target(self, task_id: str, client) -> dict:
        """按任务创建时的版本快照和规范化 Git URL 唯一定位服务。"""

        task = self.store.get(task_id)
        if task is None:
            raise PackageTaskError("PACKAGE_TASK_NOT_FOUND", "自动打包任务不存在。", 404)
        if task["stage"] == "ACCEPTED":
            task = self.store.transition(task_id, "LOCATING_TARGET")
        elif task["stage"] != "LOCATING_TARGET":
            raise PackageTaskError(
                "PACKAGE_TASK_STAGE_CONFLICT",
                "自动打包任务当前阶段不能执行目标发现。",
                409,
            )

        request = task["requestSnapshot"]
        configuration = task["configurationSnapshot"]
        repository_key = normalize_git_url(request["repositoryUrl"])
        services = client.list_services(configuration["versionId"]).get("services", [])
        matches = [
            service
            for service in services
            if normalize_git_url(str(service.get("gitUrl") or "")) == repository_key
        ]
        if len(matches) != 1:
            code = "SERVICE_NOT_FOUND" if not matches else "SERVICE_TARGET_AMBIGUOUS"
            message = "配置产品中不存在与当前仓库匹配的服务。" if not matches else "配置产品中存在多个与当前仓库匹配的服务。"
            self.store.transition(
                task_id,
                "FAILED",
                {
                    "error": {
                        "stage": "LOCATING_TARGET",
                        "code": code,
                        "message": message,
                        "retryable": False,
                    }
                },
            )
            raise PackageTaskError(code, message, 409)

        service = matches[0]
        target = {
            **configuration,
            "serviceId": service["serviceId"],
            "serviceName": str(service.get("name") or service["serviceId"]),
            "gitUrl": str(service.get("gitUrl") or request["repositoryUrl"]),
        }
        self.store.transition(task_id, "LOCATING_TARGET", {"target": target})
        return copy.deepcopy(target)

    def align_branch(self, task_id: str, client) -> dict:
        """由服务锁所有者校验并校准目标分支，完成后不恢复原分支。"""

        task = self.store.get(task_id)
        if task is None:
            raise PackageTaskError("PACKAGE_TASK_NOT_FOUND", "自动打包任务不存在。", 404)
        queue = task.get("queue") or {}
        lock_key = str(queue.get("lockKey") or "")
        if task["stage"] not in {"QUEUED", "ALIGNING_BRANCH"} or not lock_key or not self.store.owns_lock(task_id, lock_key):
            raise PackageTaskError("PACKAGE_TASK_LOCK_NOT_OWNED", "任务尚未获得服务锁。", 409)
        if task["stage"] == "QUEUED":
            task = self.store.transition(task_id, "ALIGNING_BRANCH")
        target = task["target"]
        branch = task["requestSnapshot"]["branch"]
        try:
            refs = client.list_refs(target["gitUrl"])
            if branch not in refs.get("branches", []):
                raise SystemBError("TARGET_BRANCH_NOT_FOUND", "目标 branch 不存在。", 404)
            result = client.switch_service_branch(
                target["versionId"], target["serviceId"], branch
            )
            alignment = {
                "previousBranch": result.get("previousBranch"),
                "targetBranch": branch,
                "changed": bool(result.get("changed")),
                "verified": result.get("currentBranch") == branch,
            }
            if not alignment["verified"]:
                raise SystemBError("BRANCH_UPDATE_NOT_APPLIED", "服务分支修改后验证失败。")
        except SystemBError as error:
            message = f"服务分支校准失败：{error.message}"
            self.store.transition(
                task_id,
                "FAILED",
                {
                    "error": {
                        "stage": "ALIGNING_BRANCH",
                        "code": "BRANCH_ALIGNMENT_FAILED",
                        "message": message,
                        "retryable": error.status >= 500 or error.status == 0,
                        "details": {"reasonCode": error.code},
                    }
                },
            )
            next_task_id = self.store.release(task_id, lock_key)
            if next_task_id and self.submit is not None:
                self.submit(next_task_id)
            raise PackageTaskError("BRANCH_ALIGNMENT_FAILED", message, 409) from error
        self.store.transition(task_id, "ALIGNING_BRANCH", {"branchAlignment": alignment})
        return copy.deepcopy(alignment)


class PackageTaskWorker:
    """按当前 Web 打包逻辑推进一个持久化自动任务。"""

    def __init__(
        self,
        service: PackageTaskService,
        client,
        poll_attempts: int = 60,
        poll_interval: float = 2.0,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.service = service
        self.store = service.store
        self.client = client
        self.poll_attempts = max(1, poll_attempts)
        self.poll_interval = max(0.0, poll_interval)
        self.sleeper = sleeper

    def run(self, task_id: str) -> None:
        try:
            while True:
                task = self.store.get(task_id)
                if task is None or task["stage"] in TERMINAL_STAGES:
                    return
                stage = task["stage"]
                if stage == "ACCEPTED":
                    self.service.locate_target(task_id, self.client)
                elif stage == "LOCATING_TARGET":
                    if task.get("target") is None:
                        self.service.locate_target(task_id, self.client)
                        continue
                    target = task["target"]
                    queued = self.store.enqueue(
                        task_id, f"{target['versionId']}:{target['serviceId']}"
                    )
                    if not queued["acquired"]:
                        return
                elif stage == "QUEUED":
                    queue = task.get("queue") or {}
                    if not self.store.owns_lock(task_id, str(queue.get("lockKey") or "")):
                        return
                    self.service.align_branch(task_id, self.client)
                elif stage == "ALIGNING_BRANCH":
                    if task.get("branchAlignment") is None:
                        self.service.align_branch(task_id, self.client)
                    else:
                        self._package(task_id)
                elif stage == "PACKAGING_AND_UPLOADING":
                    self._package(task_id)
                elif stage == "VERIFYING_CLOUD_RESULT":
                    self._verify_cloud(task_id)
                elif stage == "RECOVERING_CLOUD_UPLOAD":
                    self._recover_cloud(task_id)
        except PackageTaskError:
            return
        except SystemBError as error:
            self._fail(task_id, "AUTOMATION_BACKEND_REQUEST_FAILED", error.message, error.status >= 500 or error.status == 0)
        except Exception as error:  # 后台线程必须把未知异常固化为终态
            self._fail(task_id, "AUTOMATION_TASK_FAILED", str(error) or "自动打包任务执行失败。", False)

    def _package(self, task_id: str) -> None:
        task = self.store.get(task_id)
        if task is None:
            return
        execution = copy.deepcopy(task.get("execution") or {})
        request = task["requestSnapshot"]
        parameters = request["parameters"]
        package_type = parameters["packageType"]
        offline = parameters["networkType"] == "OFFLINE"
        target = task["target"]

        if not execution.get("packageRequestStarted"):
            records = self.client.list_package_records(package_type, target["versionId"], offline)
            execution["baselineRecordIds"] = [str(item.get("recordId")) for item in records]
            execution["packageRequestStarted"] = True
            execution["packageResponseReceived"] = False
            self.store.transition(task_id, "PACKAGING_AND_UPLOADING", {"execution": execution})
            payload = {
                "modules": [
                    {
                        "need_apollo": True,
                        "ref_name": request["branch"],
                        "pk": target["serviceId"],
                        "name": target["serviceName"],
                        "custom_name": target["serviceName"],
                    }
                ],
                "offline": 1 if offline else 0,
                "support_cpu": parameters["cpuArchitecture"],
                "namespace": parameters["namespace"],
                "seafile": parameters["uploadCloud"],
            }
            self.client.submit_package(package_type, target["versionId"], payload)
            execution["packageResponseReceived"] = True
            self.store.transition(task_id, "PACKAGING_AND_UPLOADING", {"execution": execution})

        for _attempt in range(self.poll_attempts):
            task = self.store.get(task_id)
            execution = copy.deepcopy((task or {}).get("execution") or {})
            records = self.client.list_package_records(package_type, target["versionId"], offline)
            record = self._select_record(records, execution)
            if record and (record.get("downloadUrl") or record.get("storagePath")):
                execution["recordId"] = str(record.get("recordId"))
                execution["storagePath"] = record.get("storagePath")
                execution["cloudTaskId"] = record.get("cloudTaskId")
                artifact = self._artifact(record, False)
                self.store.transition(
                    task_id,
                    "VERIFYING_CLOUD_RESULT",
                    {"execution": execution, "artifact": artifact},
                )
                self._release_and_wake(task_id)
                return
            self.sleeper(self.poll_interval)
        self._fail(task_id, "PACKAGE_RESULT_MISSING", "打包请求完成后未发现新的制品记录。", False)

    def _verify_cloud(self, task_id: str) -> None:
        task = self.store.get(task_id)
        if task is None:
            return
        parameters = task["requestSnapshot"]["parameters"]
        if not parameters["uploadCloud"]:
            self.store.transition(task_id, "SUCCESS")
            return

        for _attempt in range(self.poll_attempts):
            task = self.store.get(task_id)
            record = self._load_task_record(task)
            if record:
                execution = copy.deepcopy(task.get("execution") or {})
                execution["storagePath"] = record.get("storagePath")
                execution["cloudTaskId"] = record.get("cloudTaskId")
                self.store.transition(
                    task_id,
                    "VERIFYING_CLOUD_RESULT",
                    {"execution": execution, "artifact": self._artifact(record, False)},
                )
                if record.get("cloudPath") or record.get("cloudUrl"):
                    self.store.transition(task_id, "SUCCESS")
                    return
                cloud_task_id = record.get("cloudTaskId")
                if cloud_task_id:
                    progress = self.client.get_upload_progress(str(cloud_task_id))
                    if not progress.get("complete"):
                        self.sleeper(self.poll_interval)
                        continue
                    break
                break
            self.sleeper(self.poll_interval)
        else:
            self._fail(task_id, "CLOUD_UPLOAD_TIMEOUT", "现有云盘上传在限定时间内未返回地址。", True)
            return
        self.store.transition(task_id, "RECOVERING_CLOUD_UPLOAD")

    def _recover_cloud(self, task_id: str) -> None:
        task = self.store.get(task_id)
        if task is None:
            return
        execution = copy.deepcopy(task.get("execution") or {})
        record = self._load_task_record(task)
        if record and (record.get("cloudPath") or record.get("cloudUrl")):
            self.store.transition(task_id, "SUCCESS", {"artifact": self._artifact(record, bool(execution.get("cloudRecoveryStarted")))})
            return
        if not execution.get("cloudRecoveryStarted"):
            storage_path = execution.get("storagePath") or (record or {}).get("storagePath")
            if not storage_path:
                self._fail(task_id, "CLOUD_ADDRESS_MISSING", "制品缺少可用于云盘补偿的 storage_path。", False)
                return
            execution["cloudRecoveryStarted"] = True
            execution["cloudRecoveryKey"] = f"{task_id}:cloud-recovery"
            self.store.transition(task_id, "RECOVERING_CLOUD_UPLOAD", {"execution": execution})
            upload = self.client.upload_to_seafile(str(storage_path))
            execution["cloudRecoveryTaskId"] = upload["taskId"]
            self.store.transition(task_id, "RECOVERING_CLOUD_UPLOAD", {"execution": execution})
        elif not execution.get("cloudRecoveryTaskId"):
            self._fail(task_id, "CLOUD_ADDRESS_MISSING", "云盘补偿结果未知，禁止重复上传。", False)
            return

        for _attempt in range(self.poll_attempts):
            task = self.store.get(task_id)
            record = self._load_task_record(task)
            if record and (record.get("cloudPath") or record.get("cloudUrl")):
                self.store.transition(
                    task_id,
                    "SUCCESS",
                    {"artifact": self._artifact(record, True)},
                )
                return
            recovery_task_id = (task.get("execution") or {}).get("cloudRecoveryTaskId")
            if recovery_task_id:
                self.client.get_upload_progress(str(recovery_task_id))
            self.sleeper(self.poll_interval)
        self._fail(task_id, "CLOUD_ADDRESS_MISSING", "云盘补偿后仍未返回可用地址。", False)

    def _load_task_record(self, task: dict) -> "dict | None":
        request = task["requestSnapshot"]
        parameters = request["parameters"]
        records = self.client.list_package_records(
            parameters["packageType"],
            task["target"]["versionId"],
            parameters["networkType"] == "OFFLINE",
        )
        record_id = str((task.get("execution") or {}).get("recordId") or "")
        return next((item for item in records if str(item.get("recordId")) == record_id), None)

    @staticmethod
    def _select_record(records: "list[dict]", execution: dict) -> "dict | None":
        record_id = str(execution.get("recordId") or "")
        if record_id:
            return next((item for item in records if str(item.get("recordId")) == record_id), None)
        baseline = set(execution.get("baselineRecordIds") or [])
        candidates = [item for item in records if str(item.get("recordId")) not in baseline]
        if not candidates:
            return None
        return max(candidates, key=lambda item: _sortable_record_id(item.get("recordId")))

    @staticmethod
    def _artifact(record: dict, recovered: bool) -> dict:
        return {
            "name": record.get("name"),
            "downloadUrl": record.get("downloadUrl"),
            "md5": record.get("md5"),
            "cloudPath": record.get("cloudPath"),
            "cloudUrl": record.get("cloudUrl"),
            "cloudRecoveryTriggered": recovered,
        }

    def _release_and_wake(self, task_id: str) -> None:
        task = self.store.get(task_id)
        queue = (task or {}).get("queue") or {}
        lock_key = str(queue.get("lockKey") or "")
        if lock_key and self.store.owns_lock(task_id, lock_key):
            next_task_id = self.store.release(task_id, lock_key)
            if next_task_id and self.service.submit is not None:
                self.service.submit(next_task_id)

    def _fail(self, task_id: str, code: str, message: str, retryable: bool) -> None:
        task = self.store.get(task_id)
        if task is None or task["stage"] in TERMINAL_STAGES:
            return
        stage = task["stage"]
        self.store.transition(
            task_id,
            "FAILED",
            {"error": {"stage": stage, "code": code, "message": message, "retryable": retryable}},
        )
        self._release_and_wake(task_id)


def _validated_request(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise PackageTaskError("INVALID_REQUEST", "请求体不是有效 JSON 对象。")
    allowed = {"clientRequestId", "repositoryUrl", "branch", "parameters"}
    if set(payload) - allowed:
        raise PackageTaskError("INVALID_REQUEST", "自动打包请求包含未知字段。")
    request = {key: copy.deepcopy(payload.get(key)) for key in allowed}
    for key in ("clientRequestId", "repositoryUrl", "branch"):
        if not isinstance(request[key], str) or not request[key].strip():
            raise PackageTaskError("INVALID_REQUEST", f"{key} 不能为空。")
        request[key] = request[key].strip()
    parameters = request["parameters"]
    if not isinstance(parameters, dict):
        raise PackageTaskError("INVALID_PACKAGE_PARAMETERS", "打包参数无效。")
    expected = {"packageType", "networkType", "cpuArchitecture", "namespace", "uploadCloud"}
    if set(parameters) != expected:
        raise PackageTaskError("INVALID_PACKAGE_PARAMETERS", "打包参数字段不完整或包含未知字段。")
    if parameters["packageType"] not in {"INSTALL", "UPGRADE"}:
        raise PackageTaskError("INVALID_PACKAGE_TYPE", "包类型无效。")
    if parameters["networkType"] not in {"OFFLINE", "ONLINE"}:
        raise PackageTaskError("INVALID_NETWORK_TYPE", "网络类型无效。")
    if parameters["cpuArchitecture"] not in {"x86_64", "aarch64"}:
        raise PackageTaskError("INVALID_CPU_ARCHITECTURE", "CPU 架构无效。")
    if not isinstance(parameters["namespace"], str) or not parameters["namespace"].strip():
        raise PackageTaskError("INVALID_PACKAGE_PARAMETERS", "namespace 不能为空。")
    parameters["namespace"] = parameters["namespace"].strip()
    if not isinstance(parameters["uploadCloud"], bool):
        raise PackageTaskError("INVALID_PACKAGE_PARAMETERS", "uploadCloud 必须为布尔值。")
    if parameters["networkType"] == "ONLINE" and parameters["uploadCloud"]:
        raise PackageTaskError("ONLINE_CLOUD_UPLOAD_NOT_SUPPORTED", "在线包不支持上传云盘。")
    request["parameters"] = copy.deepcopy(parameters)
    return request


def _timestamp(now: "datetime | None" = None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")


def _sortable_record_id(value: object) -> "tuple[int, object]":
    try:
        return 1, int(str(value))
    except (TypeError, ValueError):
        return 0, str(value or "")
