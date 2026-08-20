## 背景

现有系统 B 已通过 HTTP API 提供登录、项目搜索、版本查询、服务查询、Git refs、Git 配置、模块更新、打包记录和 Seafile 上传等能力；当前 `ifaas-packing` 仓库是静态 Web 与 Python 本地代理，并非系统 B 后端。现有构建平台 `GitLabBuildWatch` 已具有本地 Flask 服务、SQLite、精确 Commit SHA 的 Pipeline 监控和 Windows Toast。

本变更面向单用户桌面自动化。Codex 负责理解自然语言和让用户作出选择，但 Codex 会话不作为长时间业务执行器；构建平台负责持久化发布工作流；系统 B 负责打包和 Seafile 上传。系统 B 后端位于其他服务器且使用本地文件存储，不引入数据库。

## 目标与非目标

**目标：**

- 用户明确要求打包时，Codex 能实时查询系统 B 的项目、版本、服务和分支，并基于真实数据让用户二次确认。
- 用户确认后，由构建平台立即把系统 B 中所选服务修改为当前 Git 分支，随后等待该 Commit SHA 的 GitLab 构建。
- 构建成功后，系统 B 以唯一任务 ID 异步完成打包和 Seafile 上传，构建平台可靠取得结果并通知电脑。
- 构建平台和系统 B 均可在进程重启后解释已有任务状态，且不会因创建请求重试而重复打包。
- 系统 B 自动清理创建时间超过 7 天的自动打包记录，不区分任务状态。

**非目标：**

- 不建设多用户发布平台、独立 Java Release Orchestrator、MySQL 或独立管理后台。
- 不让系统 B MCP 直接修改服务分支、创建打包任务或上传 Seafile。
- 不处理其他用户同时修改系统 B 服务分支的覆盖问题，不增加乐观锁或分支租约。
- 不在发布失败或完成后恢复系统 B 原分支。
- 不删除 Seafile 云端制品或手工打包记录。

## 决策

### 采用“Codex 发现确认、构建平台编排、系统 B 执行”的三层边界

```text
Codex
  │ 只读 MCP/CLI 查询并取得用户确认
  ▼
GitLabBuildWatch 构建平台
  │ 持久化、切换分支、等待构建、触发并跟踪打包
  ▼
系统 B
  │ 异步打包、上传 Seafile、返回制品
```

相较让 Codex 长期轮询，该方案能在会话结束或桌面程序重启后继续工作；相较新增独立编排服务，它复用现有单用户构建平台，减少部署和通信层级。内部仍以 `ReleaseWorkflowService`、`SystemBClient` 等边界隔离，未来平台化时可迁移。

### 使用共享系统 B 客户端同时支撑 CLI、MCP 和构建平台

公共客户端封装认证、分页、响应归一化、Git URL 规范化、目标检查及分支修改。CLI 与 STDIO MCP 复用同一客户端；构建平台复用其中有副作用的分支修改与自动打包调用。不得在三处分别复制系统 B 请求结构。

STDIO MCP 仅暴露 `search_projects`、`list_project_versions`、`list_version_services`、`inspect_release_target` 和 `validate_release_plan` 等只读工具。认证凭据来自本机受限配置或凭据管理，不进入 Tool 参数、模型上下文或日志。MCP 返回值只保留业务 ID、名称、分支、Git URL 和必要状态，不透传系统 B 原始用户实体及敏感字段。

### 使用 Git remote 识别当前服务，语义匹配只用于项目和版本候选排序

Codex 从自然语言提取项目关键词、版本关键词和打包参数；具体 `projectId`、`versionId`、`serviceId` 必须来自系统 B 实时响应。当前服务通过规范化本地 Git remote 与版本服务的 `git_url` 进行匹配，消除 HTTP、HTTPS、SSH 和 `.git` 后缀差异。目标分支必须存在于系统 B refs 查询结果中。

唯一候选也需要用户确认；多个候选必须展示差异并让用户明确选择；无候选时不得推送或登记发布任务。

### 在构建平台注册确认任务时立即切换系统 B 分支

Codex 将已确认的精确 Release Plan 登记到构建平台。构建平台先持久化任务，再执行：

```text
读取完整服务数据
  → 查询目标 branch 的 git_config 并取得 git_id
  → PUT 完整模块更新请求
  → 重新查询并验证目标 branch
  → READY_TO_PUSH
```

Codex 仅在收到 `READY_TO_PUSH` 后执行 `git push`。若分支已一致则跳过修改；若修改失败则停止流程。构建平台不检查确认后是否有其他用户覆盖，不使用 `expectedCurrentBranch`，也不在后续失败时恢复 `previousBranch`。`previousBranch` 只用于展示和审计。

由于本地 SQLite 与系统 B HTTP 不能形成分布式事务，构建平台先保存 `UPDATING_BRANCH` 再调用远端。重启恢复时重新查询；已是目标分支则推进，否则再次设置同一分支，该操作按幂等方式处理。

### 构建平台只接受目标 Commit SHA 的 Pipeline

发布任务以 GitLab Project ID、branch 和完整 Commit SHA 关联 Pipeline。分支上的历史成功 Pipeline 或其他 Commit 的成功 Pipeline 不得触发打包。任务登记早于 `git push`，避免快速 Pipeline 在登记前完成；如果推送失败，任务保持等待并最终超时，不回滚系统 B 分支。

构建失败、取消或等待超时为发布终态，不创建系统 B 打包任务。

### 系统 B 提供文件持久化的异步自动打包任务

`POST /api/v1/automation/package-tasks` 接受 `clientRequestId`、精确项目/版本/服务及打包参数，先生成唯一 `taskId` 并原子写入记录，再提交后台任务并返回 `202 Accepted`。相同 `clientRequestId` 在记录保留期内返回同一个 `taskId`，不得重复打包。

任务记录保存请求快照、状态、阶段、进度、制品、Seafile 地址、MD5、错误和时间。更新采用同目录临时文件写完后原子替换；查询以 `taskId` 精确定位记录。系统 B 内部复用现有打包 Service 和 Seafile 能力，不复制 Web 打包业务逻辑。

建议状态为：

```text
CREATED → PACKAGING → UPLOADING → SUCCESS
              └───────────────→ FAILED
```

若现有后端不能区分打包与上传进度，可对外使用 `PACKAGE_AND_UPLOAD_RUNNING`，桌面端不得虚构阶段。

### 自动记录按创建时间清理全部状态

系统 B 启动后执行一次清理，并每 24 小时执行一次。满足 `source = AUTOMATION` 且 `createdTime < now - 7 days` 的记录全部删除，不判断任务状态。清理同时移除 `clientRequestId` 幂等映射、进度文件和任务临时日志；不删除手工记录、Seafile 文件和本地制品。

若被清理任务仍有后台工作，清理器先标记任务停止并阻止工作线程重新写回记录。构建平台查询不到已清理的非终态任务时，将发布任务标记为 `PACKAGE_RECORD_EXPIRED`。终态结果已经由构建平台保存，不再轮询系统 B。

### 通过本机轮询实现结果回推

系统 B 位于服务器，本机构建平台通常只监听 `127.0.0.1`，因此不要求系统 B 回调桌面。构建平台按 `packageTaskId` 有界轮询系统 B；成功后立即把包名称、下载地址、Seafile 地址和 MD5 保存到 SQLite，更新工作流并发送 Windows Toast。通知点击动作打开 Seafile 地址。

## 风险与权衡

- [确认后立即修改系统 B 分支，但 Git push 或构建可能失败] → 明确接受该行为，在工作流中显示分支已修改且不自动恢复。
- [系统 B 模块更新要求完整 payload 与目标 `git_id`] → 统一封装“读取模块—查询 Git 配置—完整更新—验证”流程，禁止调用方只传 branch。
- [系统 B 原始响应含过量嵌套字段或敏感信息] → 公共客户端使用白名单 DTO，MCP、CLI 和日志均不得输出原始响应。
- [本地文件在写入中断时损坏] → 使用同目录临时文件、flush 和原子替换，并在启动时识别遗留临时文件。
- [创建任务响应丢失导致重复打包] → 构建平台使用 `releaseTaskId` 作为 `clientRequestId`，系统 B 对其建立持久化唯一映射。
- [全部状态均在 7 天后清理，长时间任务可能被删除] → 构建平台把缺失记录解释为过期终态并通知用户；清理器必须阻止工作线程重新创建记录。
- [桌面程序关闭导致轮询中断] → 构建平台将 Release Plan、Pipeline、packageTaskId 和结果写入 SQLite，启动后恢复非终态任务。
- [跨系统 change 存放在系统 B 前端仓库] → 文档明确仓库边界，实际实现分别在系统 B 后端和构建平台仓库建立对应变更，不在当前仓库混合提交外部系统代码。

## 迁移计划

1. 盘点并契约测试系统 B 现有项目、版本、服务、refs、Git 配置和模块更新接口。
2. 提取共享系统 B 客户端并交付 CLI，再包装只读 STDIO MCP 并注册到 Codex。
3. 在系统 B 后端交付自动打包创建/查询、文件持久化、幂等、Seafile 和清理能力，以 CLI 完成契约验收。
4. 在构建平台增加发布任务、分支切换、Commit SHA 监控衔接、自动打包轮询、结果快照和重启恢复。
5. 增加 Codex 明确意图规则、选择确认流程、`READY_TO_PUSH` 门禁、工作流界面和 Windows 通知。
6. 使用真实非生产项目完成端到端验收，再逐步用于日常打包。

回滚时可禁用 Codex 发布规则和构建平台发布入口，保留原 GitLab 监控及系统 B Web 手工打包。系统 B 新增任务文件和接口为增量能力，不改变现有手工打包记录；回滚程序前先停止非终态自动任务。

## 待确认事项

- 实施前需要取得系统 B 后端仓库，并确认现有 Service 层可否在后台任务中复用。
- 需要以真实接口样例确定项目、版本、服务 DTO 白名单，以及模块更新的必填字段。
- 需要确认系统 B 能否分别报告打包和 Seafile 上传阶段；不能时使用合并阶段。
- 需要确定系统 B 凭据在 Windows 上的最终存储方式，以及构建平台发布接口采用本地 HTTP 还是同 EXE CLI。
