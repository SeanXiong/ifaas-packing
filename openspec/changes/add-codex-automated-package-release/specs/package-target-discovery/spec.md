## ADDED Requirements

### Requirement: 实时查询系统 B 发布目录
系统 SHALL 通过共享客户端实时查询系统 B 的项目、项目版本和版本服务，并将这些能力同时提供给 CLI 与本地 STDIO MCP。查询结果 MUST 使用稳定的结构化字段，不得要求 Codex 解析系统 B 原始响应文本。

#### Scenario: 按自然语言关键词搜索项目
- **WHEN** Codex 从用户要求中提取项目关键词并调用项目搜索工具
- **THEN** 系统 SHALL 返回系统 B 实时存在的项目候选及其 `projectId` 和名称

#### Scenario: 查询所选项目的版本和服务
- **WHEN** 用户选择系统 B 项目后继续选择版本
- **THEN** 系统 SHALL 按精确 `projectId` 查询版本，并按所选 `versionId` 查询该版本的服务列表

### Requirement: 使用 Git 仓库匹配当前服务
系统 MUST 规范化当前仓库 remote 与系统 B 服务 `git_url`，并使用 GitLab 实例和仓库路径匹配当前服务；服务名称的语义相似度不得替代 Git 仓库匹配。

#### Scenario: HTTP 与 SSH remote 指向同一服务
- **WHEN** 本地 remote 使用 SSH 格式而系统 B 服务使用 HTTP 格式，且二者的 GitLab 实例和仓库路径相同
- **THEN** 系统 SHALL 将该服务识别为当前仓库对应服务

#### Scenario: 所选版本不存在当前服务
- **WHEN** 所选版本中没有任何服务的规范化 `git_url` 与当前仓库匹配
- **THEN** 系统 MUST 返回不可发布结果，并不得虚构或自动选择其他服务

### Requirement: 验证目标 Git 分支
系统 MUST 通过系统 B 现有 refs 接口验证当前 Git 分支是否存在，并返回系统 B 服务配置分支与目标分支是否一致。

#### Scenario: 当前分支存在但配置不同
- **WHEN** refs 包含当前 Git 分支，但服务配置分支为其他值
- **THEN** 系统 SHALL 返回 `branchExists=true` 和 `requiresBranchChange=true`，并同时返回当前配置分支与目标分支

#### Scenario: 当前分支不存在
- **WHEN** refs 不包含当前 Git 分支或标签
- **THEN** 系统 MUST 阻止发布计划通过校验

### Requirement: MCP 查询工具保持只读和最小披露
系统 B MCP MUST 只提供查询、检查和验证工具，不得提供修改服务分支、创建打包任务或上传 Seafile 的工具；所有 MCP/CLI 响应 MUST 使用字段白名单并移除凭据、密码哈希、用户实体和无关内部数据。

#### Scenario: Codex 查询版本服务
- **WHEN** MCP 从系统 B 获得包含嵌套用户或内部字段的原始响应
- **THEN** MCP SHALL 仅向 Codex 返回发布目标发现所需的 ID、名称、分支、Git URL 和状态字段

#### Scenario: Codex 尝试通过查询 MCP 修改分支
- **WHEN** Codex 枚举系统 B MCP 工具
- **THEN** 可用工具中 MUST 不存在修改服务分支或直接打包工具

