"""系统 B 查询与构建平台动作 CLI。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .client import SystemBClient, SystemBError
from .config import SystemBConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ifaas-pack")
    groups = parser.add_subparsers(dest="group", required=True)

    projects = groups.add_parser("projects")
    project_commands = projects.add_subparsers(dest="command", required=True)
    search = project_commands.add_parser("search")
    search.add_argument("--query", default="")
    search.add_argument("--page", type=int, default=1)
    search.add_argument("--page-size", type=int, default=20)

    versions = groups.add_parser("versions")
    version_commands = versions.add_subparsers(dest="command", required=True)
    version_list = version_commands.add_parser("list")
    version_list.add_argument("--project-id", required=True)

    services = groups.add_parser("services")
    service_commands = services.add_subparsers(dest="command", required=True)
    service_list = service_commands.add_parser("list")
    service_list.add_argument("--version-id", required=True)
    switch = service_commands.add_parser("switch-branch")
    switch.add_argument("--version-id", required=True)
    switch.add_argument("--service-id", required=True)
    switch.add_argument("--branch", required=True)

    refs = groups.add_parser("refs")
    ref_commands = refs.add_subparsers(dest="command", required=True)
    ref_list = ref_commands.add_parser("list")
    ref_list.add_argument("--git-url", required=True)

    target = groups.add_parser("target")
    target_commands = target.add_subparsers(dest="command", required=True)
    inspect = target_commands.add_parser("inspect")
    inspect.add_argument("--version-id", required=True)
    inspect.add_argument("--repository-url", required=True)
    inspect.add_argument("--branch", required=True)

    release = groups.add_parser("release")
    release_commands = release.add_subparsers(dest="command", required=True)
    validate = release_commands.add_parser("validate")
    validate.add_argument("--project-id", required=True)
    validate.add_argument("--version-id", required=True)
    validate.add_argument("--service-id", required=True)
    validate.add_argument("--repository-url", required=True)
    validate.add_argument("--branch", required=True)

    package = groups.add_parser("package")
    package_commands = package.add_subparsers(dest="command", required=True)
    create = package_commands.add_parser("create")
    create.add_argument("--request-file", type=Path, required=True)
    get = package_commands.add_parser("get")
    get.add_argument("--task-id", required=True)
    return parser


def execute(args: argparse.Namespace, client: SystemBClient) -> dict:
    key = (args.group, args.command)
    if key == ("projects", "search"):
        return client.search_projects(args.query, args.page, args.page_size)
    if key == ("versions", "list"):
        return client.list_versions(args.project_id)
    if key == ("services", "list"):
        return client.list_services(args.version_id)
    if key == ("services", "switch-branch"):
        return client.switch_service_branch(args.version_id, args.service_id, args.branch)
    if key == ("refs", "list"):
        return client.list_refs(args.git_url)
    if key == ("target", "inspect"):
        return client.inspect_release_target(args.version_id, args.repository_url, args.branch)
    if key == ("release", "validate"):
        return client.validate_release_plan(
            args.project_id, args.version_id, args.service_id, args.repository_url, args.branch
        )
    if key == ("package", "create"):
        payload = json.loads(args.request_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SystemBError("INVALID_REQUEST_FILE", "自动打包请求文件必须是 JSON 对象")
        return client.create_package_task(payload)
    if key == ("package", "get"):
        return client.get_package_task(args.task_id)
    raise SystemBError("UNSUPPORTED_COMMAND", "不支持的命令")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = execute(args, SystemBClient(SystemBConfig.from_environment()))
        print(json.dumps({"ok": True, "data": result}, ensure_ascii=False))
        return 0
    except (SystemBError, OSError, json.JSONDecodeError) as error:
        code = error.code if isinstance(error, SystemBError) else "CLI_INPUT_ERROR"
        print(json.dumps({"ok": False, "error": {"code": code, "message": str(error)}}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
