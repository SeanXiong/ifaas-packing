"""从 ifaas-packing 服务读取登录账号，并创建账号隔离的系统 B 客户端。"""

import os
import threading
from typing import Any

from .client import SystemBClient, SystemBError, Transport, _urllib_transport
from .config import SystemBConfig


class PackingProfileClientPool:
    """只公开账号名称；密码和 Token 始终留在 MCP 服务端。"""

    def __init__(
        self,
        packing_url: str,
        transport: "Transport | None" = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.packing_url = packing_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._transport = transport or _urllib_transport
        self._clients = {}  # type: dict[str, SystemBClient]
        self._lock = threading.Lock()

    @classmethod
    def from_environment(cls) -> "PackingProfileClientPool":
        return cls(
            os.environ.get("IFAAS_PACKING_URL", "http://192.168.14.91:36001"),
            timeout_seconds=int(os.environ.get("IFAAS_TIMEOUT_SECONDS", "30")),
        )

    def list_profiles(self) -> dict:
        profiles = self._read_profiles()
        return {"accounts": [{"username": username} for username in sorted(profiles)]}

    def authenticate(self, account: str) -> dict:
        client = self.client_for(account)
        result = client.authenticate()
        return {"authenticated": result["authenticated"], "username": account}

    def client_for(self, account: str) -> SystemBClient:
        username = str(account or "").strip()
        if not username:
            raise SystemBError("LOGIN_PROFILE_REQUIRED", "必须先选择登录账号")
        with self._lock:
            existing = self._clients.get(username)
            if existing is not None:
                return existing
            profiles = self._read_profiles()
            profile = profiles.get(username)
            if profile is None:
                raise SystemBError("LOGIN_PROFILE_NOT_FOUND", "所选登录账号不存在", 404)
            password = str(profile.get("password") or "")
            if not password:
                raise SystemBError("LOGIN_PROFILE_INVALID", "所选登录账号未配置密码")
            client = SystemBClient(
                SystemBConfig(
                    f"{self.packing_url}/api/proxy",
                    username=str(profile.get("username") or username),
                    password=password,
                    timeout_seconds=self.timeout_seconds,
                ),
                self._transport,
            )
            self._clients[username] = client
            return client

    def _read_profiles(self) -> "dict[str, dict[str, Any]]":
        status, data = self._transport(
            "GET",
            f"{self.packing_url}/api/config/login-profiles",
            {"Accept": "application/json"},
            None,
            self.timeout_seconds,
        )
        if status >= 400:
            raise SystemBError("LOGIN_PROFILES_UNAVAILABLE", "读取打包平台登录账号失败", status)
        accounts = data.get("accounts") if isinstance(data, dict) else None
        if not isinstance(accounts, dict):
            raise SystemBError("LOGIN_PROFILES_INVALID", "打包平台登录账号配置格式无效")
        return {str(key): value for key, value in accounts.items() if isinstance(value, dict)}
