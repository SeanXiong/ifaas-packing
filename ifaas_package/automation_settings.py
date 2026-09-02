"""自动打包目标设置的校验与原子持久化。"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class SettingsClient(object):
    """自动设置依赖的最小客户端接口。"""

    def get_project(self, project_id):
        raise NotImplementedError

    def list_versions(self, project_id):
        raise NotImplementedError

class AutomationSettingsError(RuntimeError):
    def __init__(self, code, message, status=400):
        RuntimeError.__init__(self, message)
        self.code = code
        self.message = message
        self.status = status

    def __str__(self) -> str:
        return self.message


class AutomationSettingsStore:
    """保存唯一全局目标，并保留首次创建审计信息。"""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> "dict | None":
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as error:
            raise AutomationSettingsError(
                "AUTOMATION_SETTINGS_CORRUPTED",
                "自动打包设置文件无法读取。",
                500,
            ) from error
        return value if isinstance(value, dict) else None

    def save(self, target: dict, username: str, now: "datetime | None" = None) -> dict:
        actor = username.strip()
        if not actor:
            raise AutomationSettingsError("AUTHENTICATED_USER_REQUIRED", "缺少当前登录用户。", 401)
        current = self.load()
        timestamp = (now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")
        created_by = str((current or {}).get("createdBy") or actor)
        created_at = str((current or {}).get("createdAt") or timestamp)
        saved = {
            "schemaVersion": 1,
            **target,
            "createdBy": created_by,
            "createdAt": created_at,
            "updatedBy": actor,
            "updatedAt": timestamp,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(saved, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, self.path)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        return saved


class AutomationSettingsService:
    def __init__(self, store: AutomationSettingsStore, client: SettingsClient):
        self.store = store
        self.client = client

    def get(self) -> dict:
        saved = self.store.load()
        if not saved:
            return {"status": "UNCONFIGURED", "target": None, "audit": None, "invalidReason": None}
        response = self._response(saved, "VALID")
        try:
            self._validated_target(saved.get("projectId"), saved.get("versionId"))
        except AutomationSettingsError as error:
            response["status"] = "INVALID"
            response["invalidReason"] = error.code
        return response

    def save(self, project_id: "str | int", version_id: "str | int", username: str) -> dict:
        target = self._validated_target(project_id, version_id)
        saved = self.store.save(target, username)
        return self._response(saved, "VALID")

    def require_valid_target(self) -> dict:
        """返回自动任务使用的配置快照，未配置或失效时拒绝创建。"""

        saved = self.store.load()
        if not saved:
            raise AutomationSettingsError(
                "AUTOMATION_TARGET_NOT_CONFIGURED",
                "自动打包目标尚未配置。",
                409,
            )
        return self._validated_target(saved.get("projectId"), saved.get("versionId"))

    def search_projects(self, query: str, page: int, page_size: int) -> dict:
        return self.client.search_projects(query, page, page_size)  # type: ignore[attr-defined]

    def search_versions(self, project_id: "str | int", query: str = "") -> dict:
        project = self.client.get_project(project_id)
        if not project.get("projectId"):
            raise AutomationSettingsError("AUTOMATION_PROJECT_NOT_FOUND", "所选项目不存在。", 404)
        keyword = query.strip().casefold()
        versions = self.client.list_versions(project_id).get("versions", [])
        if keyword:
            versions = [item for item in versions if keyword in str(item.get("name") or "").casefold()]
        return {"versions": versions}

    def _validated_target(
        self, project_id: "str | int | None", version_id: "str | int | None"
    ) -> dict:
        if project_id in (None, "") or version_id in (None, ""):
            raise AutomationSettingsError(
                "AUTOMATION_TARGET_NOT_CONFIGURED", "必须选择真实项目和产品。"
            )
        project = self.client.get_project(project_id)
        if not project.get("projectId"):
            raise AutomationSettingsError("AUTOMATION_PROJECT_NOT_FOUND", "所选项目不存在。", 404)
        versions = self.client.list_versions(project_id).get("versions", [])
        version = next(
            (item for item in versions if str(item.get("versionId")) == str(version_id)),
            None,
        )
        if version is None:
            raise AutomationSettingsError(
                "AUTOMATION_VERSION_NOT_FOUND",
                "所选产品不存在或不属于该项目。",
                404,
            )
        return {
            "projectId": project["projectId"],
            "projectName": str(project.get("name") or ""),
            "versionId": version["versionId"],
            "versionName": str(version.get("name") or ""),
        }

    @staticmethod
    def _response(saved: dict, status: str) -> dict:
        return {
            "status": status,
            "target": {
                "projectId": saved.get("projectId"),
                "projectName": saved.get("projectName"),
                "versionId": saved.get("versionId"),
                "versionName": saved.get("versionName"),
            },
            "audit": {
                "createdBy": saved.get("createdBy"),
                "createdAt": saved.get("createdAt"),
                "updatedBy": saved.get("updatedBy"),
                "updatedAt": saved.get("updatedAt"),
            },
            "invalidReason": None,
        }
