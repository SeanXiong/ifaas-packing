"""系统 B HTTP API 的共享客户端。"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from .config import SystemBConfig


Transport = Callable[[str, str, dict[str, str], bytes | None, int], tuple[int, Any]]


@dataclass
class SystemBError(RuntimeError):
    """系统 B 稳定客户端错误。"""

    code: str
    message: str
    status: int = 0

    def __str__(self) -> str:
        return self.message


class SystemBClient:
    """封装查询、分支切换和自动打包接口。"""

    def __init__(self, config: SystemBConfig, transport: Transport | None = None):
        self.config = config
        self._transport = transport or _urllib_transport
        self._token = config.token

    def search_projects(self, query: str = "", page: int = 1, page_size: int = 20) -> dict:
        params = urllib.parse.urlencode({"page": page, "pageSize": page_size, "name": query})
        data = self._request("GET", f"/api/v1/project/?{params}")
        projects = [self._project(item) for item in _as_list(data)]
        return {
            "projects": projects,
            "page": _integer(_value(data, "page"), page),
            "pageSize": _integer(_value(data, "pageSize"), page_size),
            "total": _integer(_value(data, "count"), len(projects)),
        }

    def get_project(self, project_id: str | int) -> dict:
        data = self._request("GET", f"/api/v1/project/{_quote(project_id)}")
        return self._project(_unwrap(data))

    def list_versions(self, project_id: str | int) -> dict:
        params = urllib.parse.urlencode({"project_id": project_id})
        data = self._request("GET", f"/api/v1/version/?{params}")
        return {"versions": [self._version(item) for item in _as_list(data)]}

    def list_services(self, version_id: str | int) -> dict:
        params = urllib.parse.urlencode({"version_id": version_id, "git_tag": "True"})
        data = self._request("GET", f"/api/v1/module/?{params}")
        return {"services": [self._service(item) for item in _as_list(data)]}

    def list_refs(self, git_url: str) -> dict:
        data = _unwrap(self._request("POST", "/api/v1/refs/", {"git_url": git_url}))
        return {
            "branches": _string_list(_value(data, "branches")),
            "tags": _string_list(_value(data, "tags")),
        }

    def inspect_release_target(self, version_id: str | int, repository_url: str, branch: str) -> dict:
        services = self.list_services(version_id)["services"]
        repository_key = normalize_git_url(repository_url)
        matches = [item for item in services if normalize_git_url(item.get("gitUrl", "")) == repository_key]
        result_matches = []
        for service in matches:
            refs = self.list_refs(service["gitUrl"])
            branch_exists = branch in refs["branches"] or branch in refs["tags"]
            result_matches.append({
                **service,
                "targetBranch": branch,
                "branchExists": branch_exists,
                "requiresBranchChange": service.get("branch") != branch,
            })
        return {
            "versionId": _identifier(version_id),
            "repository": repository_key,
            "targetBranch": branch,
            "serviceExists": bool(result_matches),
            "canPackage": len(result_matches) == 1 and result_matches[0]["branchExists"],
            "serviceMatches": result_matches,
        }

    def validate_release_plan(
        self,
        project_id: str | int,
        version_id: str | int,
        service_id: str | int,
        repository_url: str,
        branch: str,
    ) -> dict:
        project = self.get_project(project_id)
        versions = self.list_versions(project_id)["versions"]
        version = next((item for item in versions if str(item["versionId"]) == str(version_id)), None)
        inspection = self.inspect_release_target(version_id, repository_url, branch)
        service = next(
            (item for item in inspection["serviceMatches"] if str(item["serviceId"]) == str(service_id)),
            None,
        )
        valid = bool(project.get("projectId") and version and service and service["branchExists"])
        return {"valid": valid, "project": project, "version": version, "service": service}

    def switch_service_branch(self, version_id: str | int, service_id: str | int, branch: str) -> dict:
        raw_services = self._raw_services(version_id)
        raw = next((item for item in raw_services if str(_id(item)) == str(service_id)), None)
        if raw is None:
            raise SystemBError("SERVICE_NOT_FOUND", "所选版本中不存在目标服务", 404)
        service = self._service(raw)
        if service.get("branch") == branch:
            return {"changed": False, "previousBranch": branch, "currentBranch": branch, "service": service}
        git_url = service.get("gitUrl")
        if not git_url:
            raise SystemBError("SERVICE_GIT_URL_MISSING", "目标服务缺少 Git URL")
        git_config = _unwrap(self._request("POST", "/api/v1/git_config/", {"git_url": git_url, "branch": branch}))
        git_id = _value(git_config, "git_id")
        if git_id in (None, ""):
            raise SystemBError("GIT_CONFIG_NOT_FOUND", "目标分支缺少 git_id")
        previous = service.get("branch") or ""
        payload = {
            "name": service.get("name") or "",
            "custom_name": service.get("customName") or service.get("name") or "",
            "service_type": _integer(_value(raw, "service_type"), 1),
            "branch": branch,
            "APP_ID": _value(raw, "APP_ID") or service.get("name") or "",
            "git_config_path": _value(raw, "git_config_path") or "build_ci/config.yml",
            "is_image": _value(raw, "is_image") if _value(raw, "is_image") is not None else True,
            "version": _id(_value(raw, "version")) or _identifier(version_id),
            "git_url": git_id,
        }
        self._request("PUT", f"/api/v1/module/{_quote(service_id)}", payload)
        current = next(
            (item for item in self.list_services(version_id)["services"] if str(item["serviceId"]) == str(service_id)),
            None,
        )
        if current is None or current.get("branch") != branch:
            raise SystemBError("BRANCH_UPDATE_NOT_APPLIED", "系统 B 服务分支修改后验证失败")
        return {"changed": True, "previousBranch": previous, "currentBranch": branch, "service": current}

    def create_package_task(self, payload: dict) -> dict:
        data = _unwrap(self._request("POST", "/api/v1/automation/package-tasks", payload))
        task_id = _value(data, "taskId", "task_id")
        if not task_id:
            raise SystemBError("PACKAGE_TASK_ID_MISSING", "自动打包响应缺少 taskId")
        return {"taskId": str(task_id), "status": str(_value(data, "status") or "CREATED")}

    def get_package_task(self, task_id: str) -> dict:
        data = _unwrap(self._request("GET", f"/api/v1/automation/package-tasks/{_quote(task_id)}"))
        artifact = _value(data, "artifact")
        artifact = artifact if isinstance(artifact, dict) else {}
        error = _value(data, "error")
        error = error if isinstance(error, dict) else None
        return {
            "taskId": str(_value(data, "taskId", "task_id") or task_id),
            "status": str(_value(data, "status") or "UNKNOWN"),
            "stage": _value(data, "stage", "currentStage"),
            "progress": _safe_progress(_value(data, "progress")),
            "artifact": {
                "name": _value(artifact, "name", "packageName"),
                "downloadUrl": _value(artifact, "downloadUrl", "download_path"),
                "cloudUrl": _value(artifact, "cloudUrl", "seafile_path"),
                "md5": _value(artifact, "md5", "fileMD5"),
            },
            "error": _safe_error(error),
        }

    def _raw_services(self, version_id: str | int) -> list[dict]:
        params = urllib.parse.urlencode({"version_id": version_id, "git_tag": "True"})
        return _as_list(self._request("GET", f"/api/v1/module/?{params}"))

    def _request(self, method: str, path: str, payload: dict | None = None, retry_auth: bool = True) -> Any:
        if not self._token and path != "/rest-auth/login/":
            self._login()
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Token {self._token}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        status, data = self._transport(method, f"{self.config.base_url}{path}", headers, body, self.config.timeout_seconds)
        if status in (401, 403) and retry_auth and self.config.username and self.config.password:
            self._token = ""
            self._login()
            return self._request(method, path, payload, False)
        if status >= 400:
            raise SystemBError(_error_code(data, status), _error_message(data, status), status)
        return data

    def _login(self) -> None:
        if not self.config.username or not self.config.password:
            raise SystemBError(
                "AUTH_CONFIGURATION_MISSING",
                "未配置系统 B Token 或登录账号，请设置 IFAAS_TOKEN 或 IFAAS_USERNAME/IFAAS_PASSWORD",
            )
        body = json.dumps({"username": self.config.username, "password": self.config.password}).encode("utf-8")
        status, data = self._transport(
            "POST",
            f"{self.config.base_url}/rest-auth/login/",
            {"Content-Type": "application/json"},
            body,
            self.config.timeout_seconds,
        )
        if status >= 400:
            raise SystemBError("AUTH_FAILED", "系统 B 登录失败", status)
        token = _value(data, "key", "token")
        if not token:
            raise SystemBError("AUTH_TOKEN_MISSING", "系统 B 登录响应缺少 Token")
        self._token = str(token)

    @staticmethod
    def _project(raw: dict) -> dict:
        return {
            "projectId": _id(raw),
            "name": str(_value(raw, "name", "project_name", "projectName") or ""),
            "description": str(_value(raw, "description") or ""),
        }

    @staticmethod
    def _version(raw: dict) -> dict:
        return {
            "versionId": _id(raw),
            "name": str(_value(raw, "update_version", "name", "version") or ""),
            "enabled": not bool(_value(raw, "is_deleted")),
        }

    @staticmethod
    def _service(raw: dict) -> dict:
        git_value = _value(raw, "git_url")
        if isinstance(git_value, dict):
            git_url = str(_value(git_value, "git_url", "url") or "")
            git_id = _id(git_value)
        else:
            git_url = str(git_value or "")
            git_id = None
        return {
            "serviceId": _id(raw),
            "name": str(_value(raw, "name", "module_name") or ""),
            "customName": str(_value(raw, "custom_name", "name", "module_name") or ""),
            "branch": str(_value(raw, "branch", "ref_name", "git_branch", "tag") or ""),
            "gitUrl": git_url,
            "gitId": git_id,
            "serviceType": _integer(_value(raw, "service_type"), 1),
        }


def normalize_git_url(value: str) -> str:
    """把 HTTP/SSH Git URL 归一化为 host/path。"""

    text = (value or "").strip().replace("\\", "/")
    if not text:
        return ""
    scp = re.match(r"^[^@]+@([^:]+):(.+)$", text)
    if scp:
        host, path = scp.group(1), scp.group(2)
    else:
        parsed = urllib.parse.urlparse(text if "://" in text else f"https://{text}")
        host, path = parsed.hostname or "", parsed.path
    path = path.strip("/")
    if path.lower().endswith(".git"):
        path = path[:-4]
    return f"{host.lower()}/{path.lower()}"


def _urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: int) -> tuple[int, Any]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, _decode_json(response.read())
    except urllib.error.HTTPError as error:
        return error.code, _decode_json(error.read())
    except (urllib.error.URLError, OSError) as error:
        raise SystemBError("SYSTEM_B_UNAVAILABLE", f"无法连接系统 B：{getattr(error, 'reason', error)}") from error


def _decode_json(raw: bytes) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"message": "系统 B 返回了无法解析的响应"}


def _as_list(data: Any) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("results", "data", "list", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _unwrap(data: Any) -> dict:
    if not isinstance(data, dict):
        return {}
    nested = data.get("data")
    return nested if isinstance(nested, dict) else data


def _value(data: Any, *keys: str) -> Any:
    if not isinstance(data, dict):
        return None
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _id(data: Any) -> Any:
    if isinstance(data, dict):
        return _value(data, "id", "pk", "value")
    return data


def _identifier(value: Any) -> Any:
    return _id(value)


def _integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _quote(value: Any) -> str:
    return urllib.parse.quote(str(value), safe="")


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _error_code(data: Any, status: int) -> str:
    return str(_value(data, "errorCode", "code") or f"SYSTEM_B_HTTP_{status}")


def _error_message(data: Any, status: int) -> str:
    return str(_value(data, "message", "detail", "error") or f"系统 B 请求失败（HTTP {status}）")


def _safe_progress(value: Any) -> dict | None:
    if not isinstance(value, dict):
        return None
    return {key: value.get(key) for key in ("stage", "percent", "description", "speed") if key in value}


def _safe_error(value: Any) -> dict | None:
    if not isinstance(value, dict):
        return None
    return {key: value.get(key) for key in ("stage", "code", "message", "retryable") if key in value}
