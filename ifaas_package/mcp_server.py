"""面向 Codex 的只读 STDIO MCP Server。"""

from __future__ import annotations

import json
from typing import Any

import anyio
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from .client import SystemBClient, SystemBError
from .config import SystemBConfig
from .profiles import PackingProfileClientPool


TOOLS = [
    types.Tool(
        name="list_login_profiles",
        title="查询 IFAAS 登录账号",
        description="读取服务器端打包平台的账号候选。只返回用户名，不返回密码。项目查询前必须先调用。",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="authenticate_login_profile",
        title="使用所选账号登录 IFAAS",
        description="用户明确选择账号后登录系统 B。Token 只保存在 MCP 服务端，不返回给 Codex。",
        inputSchema={
            "type": "object",
            "properties": {"account": {"type": "string", "description": "用户选择的账号名"}},
            "required": ["account"],
        },
    ),
    types.Tool(
        name="search_projects",
        title="搜索 IFAAS 打包项目",
        description="按关键词实时搜索系统 B 项目。只返回项目 ID、名称和描述。",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "项目名称关键词"},
                "page": {"type": "integer", "minimum": 1, "default": 1},
                "pageSize": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                "account": {"type": "string", "description": "已确认并登录的账号名"},
            },
            "required": ["account"],
        },
    ),
    types.Tool(
        name="list_project_versions",
        title="查询 IFAAS 项目版本",
        description="按系统 B projectId 查询真实版本候选。",
        inputSchema={
            "type": "object",
            "properties": {
                "projectId": {"type": ["string", "integer"]},
                "account": {"type": "string"},
            },
            "required": ["projectId", "account"],
        },
    ),
    types.Tool(
        name="list_version_services",
        title="查询 IFAAS 版本服务",
        description="按 versionId 查询版本包含的服务、Git URL 和当前配置分支。",
        inputSchema={
            "type": "object",
            "properties": {
                "versionId": {"type": ["string", "integer"]},
                "account": {"type": "string"},
            },
            "required": ["versionId", "account"],
        },
    ),
    types.Tool(
        name="inspect_release_target",
        title="检查当前仓库发布目标",
        description="用当前仓库 Git URL 匹配版本服务，并检查当前分支是否存在及是否需要切换。",
        inputSchema={
            "type": "object",
            "properties": {
                "versionId": {"type": ["string", "integer"]},
                "repositoryUrl": {"type": "string"},
                "branch": {"type": "string"},
                "account": {"type": "string"},
            },
            "required": ["versionId", "repositoryUrl", "branch", "account"],
        },
    ),
    types.Tool(
        name="validate_release_plan",
        title="重新校验 IFAAS 发布计划",
        description="在用户确认后用精确 ID 重新校验项目、版本、服务、仓库和目标分支。",
        inputSchema={
            "type": "object",
            "properties": {
                "projectId": {"type": ["string", "integer"]},
                "versionId": {"type": ["string", "integer"]},
                "serviceId": {"type": ["string", "integer"]},
                "repositoryUrl": {"type": "string"},
                "branch": {"type": "string"},
                "account": {"type": "string"},
            },
            "required": ["projectId", "versionId", "serviceId", "repositoryUrl", "branch", "account"],
        },
    ),
]


def create_server(
    client: SystemBClient | None = None,
    profile_pool: PackingProfileClientPool | None = None,
) -> Server:
    direct_client = client or (None if profile_pool else SystemBClient(SystemBConfig.from_environment()))

    def selected_client(arguments: dict) -> SystemBClient:
        if profile_pool is not None:
            return profile_pool.client_for(str(arguments.get("account") or ""))
        assert direct_client is not None
        return direct_client

    async def list_tools(_context: Any, _params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=TOOLS)

    async def call_tool(_context: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        arguments = params.arguments or {}
        try:
            if params.name == "list_login_profiles":
                if profile_pool is not None:
                    result = profile_pool.list_profiles()
                else:
                    username = direct_client.config.username if direct_client is not None else ""
                    result = {"accounts": [{"username": username}]} if username else {"accounts": []}
            elif params.name == "authenticate_login_profile":
                if profile_pool is not None:
                    result = profile_pool.authenticate(str(arguments.get("account") or ""))
                else:
                    result = selected_client(arguments).authenticate()
            elif params.name == "search_projects":
                active_client = selected_client(arguments)
                result = active_client.search_projects(
                    str(arguments.get("query") or ""),
                    int(arguments.get("page") or 1),
                    int(arguments.get("pageSize") or 20),
                )
            elif params.name == "list_project_versions":
                active_client = selected_client(arguments)
                result = active_client.list_versions(arguments["projectId"])
            elif params.name == "list_version_services":
                active_client = selected_client(arguments)
                result = active_client.list_services(arguments["versionId"])
            elif params.name == "inspect_release_target":
                active_client = selected_client(arguments)
                result = active_client.inspect_release_target(
                    arguments["versionId"], arguments["repositoryUrl"], arguments["branch"]
                )
            elif params.name == "validate_release_plan":
                active_client = selected_client(arguments)
                result = active_client.validate_release_plan(
                    arguments["projectId"],
                    arguments["versionId"],
                    arguments["serviceId"],
                    arguments["repositoryUrl"],
                    arguments["branch"],
                )
            else:
                raise SystemBError("UNKNOWN_TOOL", f"未知 MCP 工具：{params.name}")
            text = json.dumps(result, ensure_ascii=False)
            return types.CallToolResult(
                content=[types.TextContent(text=text)], structuredContent=result
            )
        except (SystemBError, KeyError, TypeError, ValueError) as error:
            code = error.code if isinstance(error, SystemBError) else "INVALID_TOOL_ARGUMENTS"
            payload = {"code": code, "message": str(error)}
            return types.CallToolResult(
                content=[types.TextContent(text=json.dumps(payload, ensure_ascii=False))],
                structuredContent={"error": payload},
                isError=True,
            )

    return Server(
        "ifaas-package",
        version="1.0.0",
        title="IFAAS 打包平台查询",
        description="查询系统 B 项目、版本、服务和分支，供 Codex 准备发布计划。",
        instructions=(
            "仅在用户明确要求打包或发布时使用。先查询登录账号并让用户选择，"
            "再使用所选账号登录。所有业务 ID 必须来自工具返回；"
            "必须让用户确认项目、版本、服务、目标分支和打包参数。"
            "本 MCP 只读，不负责修改分支、推送、构建或打包。"
        ),
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def _run() -> None:
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    anyio.run(_run)


if __name__ == "__main__":
    main()
