#!/usr/bin/env python3
"""ifaas-packing 极简本地服务器。

纯 Python 标准库，零额外依赖：
- 托管 web/ 目录下的静态文件
- 代理 API 请求到后端（解决浏览器 CORS）
- 提供 config/ 目录下 JSON 配置文件的读写端点

启动：python server.py
"""

import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.request
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn

ROOT_DIR = Path(__file__).resolve().parent
WEB_DIR = ROOT_DIR / "web"
CONFIG_DIR = ROOT_DIR / "config"

SERVER_CONFIG_PATH = CONFIG_DIR / "server.json"
_SAFE_CONFIG_NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")
LONG_RUNNING_PROXY_PATHS = (
    "/api/v1/packplus/upgrade/",
    "/api/v1/packplus/install/",
)


def load_server_config() -> dict:
    try:
        data = json.loads(SERVER_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    return {
        "backend_url": str(data.get("backend_url") or "http://192.168.12.35:3000").rstrip("/"),
        "listen_host": str(data.get("listen_host") or "127.0.0.1"),
        "listen_port": int(data.get("listen_port") or 8080),
    }


class Handler(SimpleHTTPRequestHandler):
    """自定义请求处理器。"""

    server_config: dict = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # ---- helpers ----------------------------------------------------------

    def _send_cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send_json(self, data, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_json_error(self, status: int, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    def _read_json_body(self):
        raw = self._read_body()
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    # ---- HTTP methods -----------------------------------------------------

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/proxy/"):
            self._handle_proxy("GET")
        elif self.path.startswith("/api/config/"):
            self._handle_config_read()
        elif self.path == "/" or not self.path.startswith("/api/"):
            super().do_GET()
        else:
            self._send_json_error(404, "Not Found")

    def do_POST(self) -> None:  # noqa: N802
        if self.path.startswith("/api/proxy/"):
            self._handle_proxy("POST")
        elif self.path.startswith("/api/config/"):
            self._handle_config_write()
        else:
            self._send_json_error(404, "Not Found")

    def do_PUT(self) -> None:  # noqa: N802
        if self.path.startswith("/api/proxy/"):
            self._handle_proxy("PUT")
        else:
            self._send_json_error(404, "Not Found")

    def do_DELETE(self) -> None:  # noqa: N802
        if self.path.startswith("/api/proxy/"):
            self._handle_proxy("DELETE")
        else:
            self._send_json_error(404, "Not Found")

    # ---- config endpoints -------------------------------------------------

    def _config_name(self):
        """从 URL path 提取配置名，做安全校验。"""
        name = self.path[len("/api/config/"):]
        if not name or not _SAFE_CONFIG_NAME.match(name):
            return None
        return name

    def _handle_config_read(self) -> None:
        name = self._config_name()
        if name is None:
            self._send_json_error(400, "无效的配置名。")
            return
        path = CONFIG_DIR / f"{name}.json"
        if not path.exists():
            self._send_json_error(404, f"配置 {name} 不存在。")
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._send_json(data)
        except (OSError, json.JSONDecodeError) as exc:
            self._send_json_error(500, f"读取配置失败：{exc}")

    def _handle_config_write(self) -> None:
        name = self._config_name()
        if name is None:
            self._send_json_error(400, "无效的配置名。")
            return
        body = self._read_json_body()
        if body is None:
            self._send_json_error(400, "请求体不是有效 JSON。")
            return
        path = CONFIG_DIR / f"{name}.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self._send_json({"ok": True, "name": name})
        except OSError as exc:
            self._send_json_error(500, f"写入配置失败：{exc}")

    # ---- API proxy --------------------------------------------------------

    def _handle_proxy(self, method: str) -> None:
        backend = self.server_config.get("backend_url", "http://192.168.12.35:3000")
        target_path = self.path[len("/api/proxy"):]  # 保留 /rest-auth/login/ 这样的路径
        url = f"{backend}{target_path}"
        timeout = None if any(target_path.startswith(path) for path in LONG_RUNNING_PROXY_PATHS) else 30

        body = self._read_body()
        req = urllib.request.Request(url, data=body, method=method)

        # 透传关键请求头
        for header in ("Authorization", "Content-Type"):
            value = self.headers.get(header)
            if value:
                req.add_header(header, value)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_body = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type",
                                 resp.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(resp_body)))
                self._send_cors()
                self.end_headers()
                self.wfile.write(resp_body)
        except urllib.error.HTTPError as exc:
            err_body = exc.read() if exc.fp else b"{}"
            self.send_response(exc.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err_body)))
            self._send_cors()
            self.end_headers()
            self.wfile.write(err_body)
        except urllib.error.URLError as exc:
            self._send_json_error(502, f"后端连接失败：{exc.reason}")
        except OSError as exc:
            self._send_json_error(502, f"代理请求失败：{exc}")

    # ---- override logging -------------------------------------------------

    def log_message(self, fmt: str, *args) -> None:  # type: ignore[override]
        print(f"[{self.log_date_time_string()}] {fmt % args}", file=sys.stderr)


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """每个请求独立处理，避免慢代理请求阻塞其他浏览器请求。"""

    daemon_threads = True


def main() -> int:
    config = load_server_config()
    Handler.server_config = config

    host = config["listen_host"]
    port = config["listen_port"]

    # 确保 Web 和 Config 目录存在
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(str(WEB_DIR))

    # MIME 类型补充
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/html", ".html")
    mimetypes.add_type("image/svg+xml", ".svg")

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"ifaas-packing 本地服务器已启动")
    print(f"  地址：http://{host}:{port}")
    print(f"  后端：{config['backend_url']}")
    print(f"  按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
