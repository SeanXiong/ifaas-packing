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


TOOLS = [
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
            },
        },
    ),
    types.Tool(
        name="list_project_versions",
        title="查询 IFAAS 项目版本",
        description="按系统 B projectId 查询真实版本候选。",
        inputSchema={
            "type": "object",
            "properties": {"projectId": {"type": ["string", "integer"]}},
            "required": ["projectId"],
        },
    ),
    types.Tool(
        name="list_version_services",
        title="查询 IFAAS 版本服务",
        description="按 versionId 查询版本包含的服务、Git URL 和当前配置分支。",
        inputSchema={
            "type": "object",
            "properties": {"versionId": {"type": ["string", "integer"]}},
            "required": ["versionId"],
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
            },
            "required": ["versionId", "repositoryUrl", "branch"],
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
            },
            "required": ["projectId", "versionId", "serviceId", "repositoryUrl", "branch"],
        },
    ),
]


def create_server(client: SystemBClient | None = None) -> Server:
    active_client = client or SystemBClient(SystemBConfig.from_environment())

    async def list_tools(_context: Any, _params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=TOOLS)

    async def call_tool(_context: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        arguments = params.arguments or {}
        try:
            if params.name == "search_projects":
                result = active_client.search_projects(
                    str(arguments.get("query") or ""),
                    int(arguments.get("page") or 1),
                    int(arguments.get("pageSize") or 20),
                )
            elif params.name == "list_project_versions":
                result = active_client.list_versions(arguments["projectId"])
            elif params.name == "list_version_services":
                result = active_client.list_services(arguments["versionId"])
            elif params.name == "inspect_release_target":
                result = active_client.inspect_release_target(
                    arguments["versionId"], arguments["repositoryUrl"], arguments["branch"]
                )
            elif params.name == "validate_release_plan":
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
            "仅在用户明确要求打包或发布时使用。所有业务 ID 必须来自工具返回；"
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
