## ADDED Requirements

### Requirement: 仅由明确打包意图触发发布流程
Codex MUST 仅在用户明确要求打包、生成安装包或升级包、构建成功后发布或上传云盘时启动发布目标发现；普通代码修改、提交或推送请求不得隐式创建发布任务。

#### Scenario: 用户只要求提交代码
- **WHEN** 用户要求修改并提交代码但未表达打包或发布意图
- **THEN** Codex MUST 不查询系统 B 发布目录且不得创建发布任务

#### Scenario: 用户明确要求构建成功后打包
- **WHEN** 用户要求提交代码并在构建成功后生成升级包
- **THEN** Codex SHALL 在完成测试和本地 commit 后启动发布目标发现流程

### Requirement: 发布目标必须由用户二次确认
Codex MUST 使用系统 B 实时候选让用户选择项目和版本，并在展示代码仓库、当前分支、Commit SHA、系统 B 项目、版本、服务、当前配置分支、目标分支及打包参数后获得明确确认。

#### Scenario: 只有一个高置信度候选
- **WHEN** 系统 B 只返回一个匹配项目、版本和服务
- **THEN** Codex MUST 仍展示完整发布方案并等待用户确认

#### Scenario: 存在多个候选版本
- **WHEN** 系统 B 返回多个可能版本
- **THEN** Codex SHALL 展示候选差异并要求用户明确选择，不得默认取第一项

#### Scenario: 用户取消确认
- **WHEN** 用户取消或拒绝发布方案
- **THEN** Codex MUST 不登记发布任务、不修改系统 B 且不因发布流程执行 `git push`

### Requirement: 发布计划使用精确 ID 并在登记前重新校验
确认后的 Release Plan MUST 固化真实 `projectId`、`versionId`、`serviceId`、目标分支和打包参数；Codex MUST 在登记前调用验证能力确认目标仍然存在，不得从自然语言生成业务 ID。

#### Scenario: 确认后的版本已不存在
- **WHEN** 登记前重新校验发现 `versionId` 已不可用或服务不再属于该版本
- **THEN** Codex MUST 停止登记并要求用户重新选择

### Requirement: 构建平台准备完成后才允许推送
Codex SHALL 先把确认后的 Release Plan 登记到构建平台；只有构建平台已保存任务、完成系统 B 分支切换并返回 `READY_TO_PUSH` 后，Codex 才能执行 `git push`。

#### Scenario: 分支切换成功
- **WHEN** 构建平台返回 `READY_TO_PUSH`
- **THEN** Codex SHALL 推送包含已登记 Commit SHA 的当前分支

#### Scenario: 分支切换失败
- **WHEN** 构建平台返回 `BRANCH_UPDATE_FAILED`
- **THEN** Codex MUST 不执行发布流程对应的 `git push`，并向用户报告失败原因

