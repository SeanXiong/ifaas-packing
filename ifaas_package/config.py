"""系统 B 客户端配置。"""

import json
import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


class SystemBConfig:
    """系统 B 连接配置。"""

    def __init__(
        self,
        base_url,
        username="",
        password="",
        token="",
        timeout_seconds=30,
    ):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.token = token
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "SystemBConfig":
        """从环境变量和现有本地配置读取连接信息。"""

        config_dir = Path(os.environ.get("IFAAS_CONFIG_DIR") or ROOT_DIR / "config")
        server = _read_json(config_dir / "server.json")
        base_url = str(
            os.environ.get("IFAAS_BACKEND_URL")
            or server.get("backend_url")
            or "http://127.0.0.1:3000"
        ).rstrip("/")
        username = os.environ.get("IFAAS_USERNAME", "").strip()
        password = os.environ.get("IFAAS_PASSWORD", "")
        token = os.environ.get("IFAAS_TOKEN", "").strip()
        if not token and (not username or not password):
            profile_username, profile_password = _read_login_profile(config_dir)
            username = username or profile_username
            password = password or profile_password
        timeout = int(os.environ.get("IFAAS_TIMEOUT_SECONDS") or 30)
        return cls(base_url, username, password, token, timeout)


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_login_profile(config_dir: Path) -> "tuple[str, str]":
    data = _read_json(config_dir / "login-profiles.json")
    accounts = data.get("accounts")
    if not isinstance(accounts, dict) or not accounts:
        return "", ""
    preferred = os.environ.get("IFAAS_PROFILE", "").strip()
    if preferred:
        profile = accounts.get(preferred)
    elif len(accounts) == 1:
        profile = next(iter(accounts.values()))
    else:
        return "", ""
    if not isinstance(profile, dict):
        return "", ""
    return str(profile.get("username") or ""), str(profile.get("password") or "")
