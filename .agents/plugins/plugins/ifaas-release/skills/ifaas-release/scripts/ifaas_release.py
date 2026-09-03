#!/usr/bin/env python3
"""显式 IFAAS 发布登记 CLI；凭据只从进程环境读取。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class ReleaseError(RuntimeError):
    pass


def git_output(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        raise ReleaseError(result.stderr.strip() or f"git {' '.join(arguments)} 执行失败。")
    return result.stdout.strip()


def normalize_git_url(value: str) -> str:
    text = value.strip().replace("\\", "/")
    scp = re.match(r"^[^@]+@([^:]+):(.+)$", text)
    if scp:
        host, path = scp.group(1), scp.group(2)
    else:
        parsed = urllib.parse.urlparse(text if "://" in text else f"https://{text}")
        host, path = parsed.hostname or "", parsed.path
    path = path.strip("/")
    if path.lower().endswith(".git"):
        path = path[:-4]
    if not host or not path:
        raise ReleaseError("Git remote 无法规范化。")
    return f"https://{host.lower()}/{path.lower()}.git"


def build_request(args: argparse.Namespace) -> dict:
    repository = Path(args.repository).resolve()
    remote = git_output(repository, "remote", "get-url", args.remote)
    branch = git_output(repository, "branch", "--show-current")
    commit_sha = git_output(repository, "rev-parse", "HEAD")
    if not branch:
        raise ReleaseError("当前 Git 仓库处于 detached HEAD，缺少可发布 branch。")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit_sha):
        raise ReleaseError("当前 Git 仓库缺少完整 Commit SHA。")
    parameters = {
        "packageType": args.package_type,
        "networkType": args.network_type,
        "cpuArchitecture": args.cpu_architecture,
        "namespace": args.namespace.strip(),
        "uploadCloud": args.upload_cloud,
    }
    if not parameters["namespace"]:
        raise ReleaseError("namespace 不能为空。")
    if parameters["networkType"] == "ONLINE" and parameters["uploadCloud"]:
        raise ReleaseError("在线包不支持上传云盘。")
    request = {
        "gitlabProjectId": args.gitlab_project_id,
        "repositoryUrl": normalize_git_url(remote),
        "branch": branch,
        "commitSha": commit_sha,
        "packageTrigger": args.package_trigger,
        "parameters": parameters,
    }
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8")
    request["clientRequestId"] = f"codex-{hashlib.sha256(canonical).hexdigest()[:32]}"
    return {"clientRequestId": request.pop("clientRequestId"), **request}


def platform_config() -> tuple[str, str]:
    base_url = os.environ.get("IFAAS_BUILD_PLATFORM_URL", "").strip().rstrip("/")
    token = os.environ.get("IFAAS_BUILD_PLATFORM_TOKEN", "").strip()
    if not base_url:
        raise ReleaseError("缺少环境变量 IFAAS_BUILD_PLATFORM_URL。")
    if not re.match(r"^https?://", base_url):
        raise ReleaseError("IFAAS_BUILD_PLATFORM_URL 必须是 HTTP(S) 地址。")
    if not token:
        raise ReleaseError("缺少环境变量 IFAAS_BUILD_PLATFORM_TOKEN。")
    return base_url, token


def request_json(method: str, url: str, token: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise ReleaseError(f"构建平台拒绝请求（HTTP {error.code}）。") from error
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as error:
        raise ReleaseError("无法读取构建平台响应。") from error
    if not isinstance(data, dict):
        raise ReleaseError("构建平台响应不是 JSON 对象。")
    return data


def register(request: dict) -> dict:
    base_url, token = platform_config()
    response = request_json("POST", f"{base_url}/api/release-tasks", token, request)
    expected_statuses = (
        {"CREATING_PACKAGE", "PACKAGE_RUNNING"}
        if request.get("packageTrigger") == "DIRECT"
        else {"READY_TO_PUSH"}
    )
    if response.get("status") not in expected_statuses or not response.get("releaseTaskId"):
        raise ReleaseError("构建平台未返回预期状态或 releaseTaskId。")
    return {
        "releaseTaskId": str(response["releaseTaskId"]),
        "status": str(response["status"]),
    }


def release(args: argparse.Namespace, request: dict) -> dict:
    repository = Path(args.repository).resolve()
    if git_output(repository, "status", "--porcelain"):
        raise ReleaseError("工作区仍有未提交修改，请完成检查和 commit 后重试。")
    registered = register(request)
    if request.get("packageTrigger") == "DIRECT":
        return registered
    result = subprocess.run(
        ["git", "push", args.remote, request["branch"]],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        base_url, token = platform_config()
        task_id = urllib.parse.quote(registered["releaseTaskId"], safe="")
        request_json(
            "POST",
            f"{base_url}/api/release-tasks/{task_id}/push-failed",
            token,
            {"code": "PUSH_FAILED", "message": "git push 执行失败。"},
        )
        raise ReleaseError("git push 失败，构建平台任务已标记为 PUSH_FAILED。")
    return {"releaseTaskId": registered["releaseTaskId"], "status": "WAITING_BUILD"}


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="登记 IFAAS 自动打包发布")
    value.add_argument("command", choices=("prepare", "register", "release"))
    value.add_argument("--repository", default=".")
    value.add_argument("--remote", default="origin")
    value.add_argument("--gitlab-project-id", required=True)
    value.add_argument("--package-type", choices=("INSTALL", "UPGRADE"), required=True)
    value.add_argument("--network-type", choices=("OFFLINE", "ONLINE"), required=True)
    value.add_argument("--cpu-architecture", choices=("x86_64", "aarch64"), required=True)
    value.add_argument("--namespace", required=True)
    value.add_argument("--upload-cloud", action="store_true")
    value.add_argument(
        "--package-trigger", choices=("DIRECT", "AFTER_PIPELINE"), default="AFTER_PIPELINE"
    )
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        release_request = build_request(args)
        if args.command == "prepare":
            result = release_request
        elif args.command == "register":
            result = register(release_request)
        else:
            result = release(args, release_request)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except ReleaseError as error:
        print(json.dumps({"error": {"code": "IFAAS_RELEASE_FAILED", "message": str(error)}}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
