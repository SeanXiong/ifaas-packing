# IFAAS 项目打包工具

一个轻量级 HTML 单页打包工具，通过本地 Python 标准库服务器运行。

## 功能

- 登录后自动保存 Token，用于后续接口请求。
- 左侧支持项目名称实时搜索、收藏项目、收藏持久化。
- 中间按项目加载版本。
- 右侧按版本加载组件，支持全选、局部过滤、组件勾选。
- 支持离线/在线升级包、CPU 架构、命名空间配置。
- 支持按服务获取 Git 分支并修改当前服务分支。
- 点击"开始打包"后按接口规范提交 JSON。
- 支持查看升级包记录、复制下载地址、上传网盘。

## 启动方式

Web 与自动打包主服务零额外依赖，支持 Python 3.6.9 及以上版本：

```bash
python server.py
```

可选 MCP 服务依赖独立的 `mcp` 包，不属于自动发布主链路，也不承诺兼容 Python 3.6。

浏览器打开 `http://127.0.0.1:8080`，登录后即可使用。

## 自动打包与 Codex Skill

自动打包第一阶段直接复用当前页面已经使用的打包接口和字段，不依赖完整状态枚举：

- 新记录出现 `download_path` 或 `storage_path` 即认为制品可用。
- 新记录出现 `seafile_path` 即认为云盘结果可用。
- 存在 `task_id_2seafile` 时只进行有界等待；没有进行中的上传且云盘地址仍缺失时，仅补偿上传一次。

服务启动后提供以下本地编排接口：

```text
GET  /api/automation/settings
PUT  /api/automation/settings
GET  /api/automation/projects
GET  /api/automation/projects/{projectId}/versions
POST /api/automation/package-tasks
GET  /api/automation/package-tasks/{packageTaskId}
```

自动任务沿用页面登录 Token，也可以在服务重启恢复任务时通过 `IFAAS_TOKEN` 或
`IFAAS_USERNAME`/`IFAAS_PASSWORD` 提供后端凭据。执行器可用
`IFAAS_AUTOMATION_WORKERS`、`IFAAS_AUTOMATION_POLL_ATTEMPTS` 和
`IFAAS_AUTOMATION_POLL_INTERVAL` 调整并发数及轮询边界。

团队插件位于 `.agents/plugins`。安装后必须在新 Codex 任务中显式输入 `$ifaas-release`
才会登记发布；普通修改、提交、推送或自然语言提到打包均不会触发：

```powershell
powershell -ExecutionPolicy Bypass -File .agents\plugins\plugins\ifaas-release\scripts\install.ps1
$env:IFAAS_BUILD_PLATFORM_URL = 'http://127.0.0.1:8765'
$env:IFAAS_BUILD_PLATFORM_TOKEN = '<构建平台令牌>'
```

Skill 通过本地 CLI/HTTP 调用构建平台，第一阶段不需要安装或注册 MCP。

## 可选查询 CLI 与旧 MCP 工具

共享 CLI 从 `config/server.json` 读取打包后端地址，并复用登录配置；也可使用
`IFAAS_BACKEND_URL`、`IFAAS_TOKEN` 或 `IFAAS_USERNAME`/`IFAAS_PASSWORD` 覆盖。所有命令只输出裁剪后的业务字段。

```powershell
python ifaas_pack.py projects search --query 基础平台
python ifaas_pack.py versions list --project-id 1001
python ifaas_pack.py services list --version-id 2001
python ifaas_pack.py target inspect --version-id 2001 --repository-url <git-url> --branch <branch>
```

`ifaas_mcp.py` 是只读 STDIO MCP Server，只提供项目、版本、服务、refs 匹配和发布计划校验；
不提供切换分支或创建打包任务工具。Codex CLI 可用以下命令注册（替换 Python 路径）：

```powershell
codex mcp add ifaas-package -- python D:\workspace\ifaas-packing\ifaas_mcp.py
```

### 可选服务器 MCP

`ifaas-packing` 部署在服务器时，使用 Streamable HTTP MCP，接收方不需要复制本仓库或在本机运行 MCP：

```powershell
python -m pip install -r requirements-mcp-http.txt
$env:IFAAS_MCP_ACCESS_TOKEN = '<部署令牌>'
$env:IFAAS_PACKING_URL = 'http://192.168.14.91:36001'
$env:IFAAS_MCP_HOST = '127.0.0.1'
$env:IFAAS_MCP_PORT = '36003'
python ifaas_mcp_http.py
```

当前服务器直接对外暴露 MCP 端口，客户端连接 `http://<服务器IP>:36003/mcp`。
生产环境应通过防火墙限制来源地址，并使用 `IFAAS_MCP_ACCESS_TOKEN` 鉴权。MCP 首先读取
`/api/config/login-profiles`，只向 Codex 返回账号名；用户选择账号后，服务端通过
`/api/proxy/rest-auth/login/` 登录，密码和 Token 均不会返回 Codex。

该 MCP 只用于兼容旧的查询流程，不是 `$ifaas-release` 或自动打包的运行依赖。

有副作用的旧 CLI 命令保留用于兼容和诊断：

```powershell
python ifaas_pack.py services switch-branch --version-id 2001 --service-id 3001 --branch release-2.0
python ifaas_pack.py package create --request-file release-request.json
python ifaas_pack.py package get --task-id pkg_001
```

新的自动任务应使用本服务的 `/api/automation/package-tasks` 创建和查询接口。

## 配置文件

所有配置以 JSON 文件保存在 `config/` 目录：

| 文件 | 用途 |
|------|------|
| `config/server.json` | 后端 API 地址和监听端口 |
| `config/favorites.json` | 收藏的项目 ID 列表 |
| `config/credentials.json` | 记住的登录凭据 |

## 接口配置

后端地址修改：编辑 `config/server.json` 中的 `backend_url` 字段。

## 项目结构

```
ifaas-packing/
├── server.py                  # 极简本地服务器（Python 标准库）
├── web/                       # HTML 前端
│   ├── index.html             # 单页应用
│   ├── css/app.css            # 样式
│   └── js/
│       ├── api.js             # API 客户端
│       ├── config.js          # 配置读写
│       ├── app.js             # 主应用逻辑
│       └── utils.js           # 工具函数
├── config/                    # 运行时配置文件
│   ├── server.json
│   ├── favorites.json
│   └── credentials.json
└── README.md
```
