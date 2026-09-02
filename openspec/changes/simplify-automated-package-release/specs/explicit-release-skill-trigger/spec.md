## ADDED Requirements

### Requirement: 只有显式调用发布 Skill 才启动自动发布
Codex MUST 仅在用户显式调用 `$ifaas-release` 时加载自动发布流程并登记发布任务；普通修改、提交、推送或未显式调用 Skill 的自然语言描述 MUST 不得触发。

#### Scenario: 用户显式调用 Skill
- **WHEN** 用户输入 `$ifaas-release` 并提供或接受打包参数
- **THEN** Codex SHALL 读取当前 Git 上下文并准备自动发布计划

#### Scenario: 用户只要求提交或推送
- **WHEN** 用户未显式调用 `$ifaas-release`，只要求修改、提交、推送或构建
- **THEN** Codex MUST 不得登记发布任务或调用自动打包链路

#### Scenario: 用户自然语言提到打包但未调用 Skill
- **WHEN** 用户只以普通自然语言提出打包要求但未显式调用 `$ifaas-release`
- **THEN** Codex MUST 不得自动登记任务，并可提示用户显式调用 Skill

### Requirement: Skill 收集确定性 Git 与打包上下文
Skill MUST 从当前仓库读取规范化 remote、当前 branch 和完整 Commit SHA，并 SHALL 收集明确的包类型、网络类型、CPU 架构、namespace 和云盘选项；不得从自然语言生成项目、版本或服务业务 ID。

#### Scenario: 当前仓库上下文完整
- **WHEN** 当前仓库存在 remote、非空 branch 和本地 Commit
- **THEN** Skill SHALL 生成包含 `repositoryUrl`、branch、完整 Commit SHA 和打包参数的发布请求

#### Scenario: 缺少必要 Git 上下文
- **WHEN** 当前目录不是可发布 Git 仓库，或缺少 remote、branch、Commit 中任一项
- **THEN** Skill MUST 停止登记并报告缺失信息

### Requirement: Skill 在推送前登记发布任务
Skill MUST 在本地检查和 commit 完成后先向构建平台幂等登记精确发布任务，并 SHALL 仅在构建平台确认任务已持久化且允许推送后执行 `git push`。

#### Scenario: 发布任务登记成功
- **WHEN** 构建平台返回唯一 `releaseTaskId` 和 `READY_TO_PUSH`
- **THEN** Skill SHALL 推送包含已登记 Commit SHA 的当前分支，并向用户输出任务 ID 和等待构建状态

#### Scenario: 发布任务登记失败
- **WHEN** 构建平台拒绝或无法持久化发布任务
- **THEN** Skill MUST 不执行发布流程对应的 push，并报告稳定错误

#### Scenario: 推送失败
- **WHEN** 任务登记后 `git push` 失败
- **THEN** Skill SHALL 向构建平台报告 `PUSH_FAILED`，且构建平台 MUST 不创建打包任务

### Requirement: 第一阶段不依赖 MCP
显式发布 Skill SHALL 通过本地 CLI 或受控脚本调用构建平台 HTTP API，并 MUST 从模型上下文之外读取凭据；MCP 不得成为启动或完成自动发布的必要条件。

#### Scenario: 未安装打包 MCP
- **WHEN** 当前 Codex 环境已安装 Skill 和所需 CLI/脚本但没有注册打包 MCP
- **THEN** 用户仍 SHALL 能完成发布登记和推送流程
