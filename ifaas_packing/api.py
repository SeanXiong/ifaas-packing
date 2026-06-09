from __future__ import annotations

from dataclasses import dataclass
import copy
import json
import logging
import time
from typing import Any

import requests


BASE_URL = "http://192.168.12.35:3000"
LOGIN_URL = f"{BASE_URL}/rest-auth/login/"
LOGGER = logging.getLogger("ifaas_packing.api")


class ApiError(RuntimeError):
    """业务接口请求失败。"""


@dataclass
class ApiClient:
    username: str = "sujiangang"
    password: str = "Intellif@123"
    timeout: int = 20
    token: str | None = None

    def login(self) -> str:
        payload = {"username": self.username, "password": self.password}
        response = self._request("POST", LOGIN_URL, json=payload, auth_required=False)
        data = self._parse_response(response)
        token = data.get("key")
        if not token:
            raise ApiError("登录成功但响应中未找到 Token key")
        self.token = str(token)
        return self.token

    def search_projects(self, keyword: str = "") -> list[dict[str, Any]]:
        data = self._get(
            "/api/v1/project/",
            params={"page": 1, "pageSize": 100, "name": keyword},
        )
        return self._as_list(data)

    def get_versions(self, project_id: int | str) -> list[dict[str, Any]]:
        data = self._get("/api/v1/version/", params={"project_id": project_id})
        return self._as_list(data)

    def get_modules(self, version_id: int | str) -> list[dict[str, Any]]:
        data = self._get(
            "/api/v1/module/",
            params={"version_id": version_id, "git_tag": "True"},
        )
        return self._as_list(data)

    def get_update_records(self, version_id: int | str, offline_status: bool = True) -> list[dict[str, Any]]:
        data = self._get(
            "/api/v1/recordsprojectupdate/",
            params={"version_id": version_id, "offline_status": str(offline_status)},
        )
        return self._as_list(data)

    def submit_pack(self, version_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._post(f"/api/v1/packplus/upgrade/{version_id}", json=payload)
        return data if isinstance(data, dict) else {"data": data}

    def get_refs(self, git_url: str) -> dict[str, Any]:
        data = self._post("/api/v1/refs/", json={"git_url": git_url})
        return data if isinstance(data, dict) else {"data": data}

    def get_git_config(self, git_url: str, branch: str) -> dict[str, Any]:
        data = self._post("/api/v1/git_config/", json={"git_url": git_url, "branch": branch})
        return data if isinstance(data, dict) else {"data": data}

    def update_module(self, module_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._put(f"/api/v1/module/{module_id}", json=payload)
        return data if isinstance(data, dict) else {"data": data}

    def upload_to_seafile(self, storage_path: str) -> dict[str, Any]:
        data = self._post("/api/v1/package/2seafile", json={"storagePath": storage_path})
        return data if isinstance(data, dict) else {"data": data}

    def get_upload_progress(self, task_id: str) -> dict[str, Any]:
        data = self._get(
            f"/api/v1/package/progress/{task_id}",
            params={"task_id": task_id},
        )
        return data if isinstance(data, dict) else {"data": data}

    def _headers(self) -> dict[str, str]:
        if not self.token:
            self.login()
        return {"Authorization": f"Token {self.token}"}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self._request("GET", f"{BASE_URL}{path}", params=params)
        return self._parse_response(response)

    def _post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        response = self._request("POST", f"{BASE_URL}{path}", json=json)
        return self._parse_response(response)

    def _put(self, path: str, json: dict[str, Any] | None = None) -> Any:
        response = self._request("PUT", f"{BASE_URL}{path}", json=json)
        return self._parse_response(response)

    def _request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        auth_required: bool = True,
    ) -> requests.Response:
        headers = self._headers() if auth_required else None
        started = time.perf_counter()
        LOGGER.info(
            "API Request %s %s params=%s body=%s headers=%s",
            method,
            url,
            self._to_log_text(params),
            self._to_log_text(self._mask_payload(json)),
            self._to_log_text(self._mask_headers(headers)),
        )
        try:
            response = requests.request(
                method,
                url,
                params=params,
                json=json,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException:
            elapsed_ms = (time.perf_counter() - started) * 1000
            LOGGER.exception("API Request failed %s %s elapsed=%.1fms", method, url, elapsed_ms)
            raise

        elapsed_ms = (time.perf_counter() - started) * 1000
        LOGGER.info(
            "API Response %s %s status=%s elapsed=%.1fms body=%s",
            method,
            response.url,
            response.status_code,
            elapsed_ms,
            self._response_preview(response),
        )
        return response

    @staticmethod
    def _parse_response(response: requests.Response) -> Any:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            text = response.text[:500] if response.text else ""
            raise ApiError(f"HTTP {response.status_code}: {text}") from exc
        try:
            return response.json()
        except ValueError as exc:
            raise ApiError("接口返回不是合法 JSON") from exc

    @staticmethod
    def _mask_headers(headers: dict[str, str] | None) -> dict[str, str] | None:
        if not headers:
            return headers
        masked = dict(headers)
        if "Authorization" in masked:
            masked["Authorization"] = "Token ***"
        return masked

    @staticmethod
    def _mask_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if payload is None:
            return None
        masked = copy.deepcopy(payload)
        for key in ("password", "token", "key", "Authorization"):
            if key in masked:
                masked[key] = "***"
        return masked

    @staticmethod
    def _to_log_text(value: Any) -> str:
        if value is None:
            return "-"
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except TypeError:
            return str(value)

    @staticmethod
    def _response_preview(response: requests.Response, limit: int = 1200) -> str:
        try:
            data = response.json()
        except ValueError:
            data = None

        if isinstance(data, dict):
            text = ApiClient._to_log_text(ApiClient._mask_payload(data))
        else:
            text = response.text or ""
        text = text.replace("\r", "\\r").replace("\n", "\\n")
        if len(text) > limit:
            return text[:limit] + "...<truncated>"
        return text

    @staticmethod
    def _as_list(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("results", "data", "list", "items"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []
