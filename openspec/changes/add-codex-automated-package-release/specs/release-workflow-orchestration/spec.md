## ADDED Requirements

### Requirement: 构建平台持久化精确发布计划
构建平台 MUST 在调用系统 B 修改分支前持久化 Release Plan，包括 GitLab Project ID、仓库、分支、完整 Commit SHA、系统 B 项目/版本/服务 ID、分支和打包参数。

#### Scenario: 接收已确认的发布计划
- **WHEN** Codex 向构建平台登记通过重新校验的 Release Plan
- **THEN** 构建平台 SHALL 生成唯一 `releaseTaskId`、保存请求快照并进入分支更新阶段

#### Scenario: 重复登记同一发布计划
- **WHEN** Codex 使用同一 `clientRequestId` 重复登记
- **THEN** 构建平台 SHALL 返回已有发布任务且不得重复创建工作流

### Requirement: 构建平台负责修改系统 B 服务分支
构建平台 MUST 在任务确认阶段读取完整服务和目标 Git 配置，调用系统 B 模块更新接口把服务切换为当前 Git 分支，并重新查询验证；构建平台不得在后续成功或失败时自动恢复原分支。

#### Scenario: 服务分支需要修改
- **WHEN** 系统 B 服务当前分支与 Release Plan 目标分支不同
- **THEN** 构建平台 SHALL 查询目标分支 `git_id`、提交完整模块更新并在验证成功后进入 `READY_TO_PUSH`

#### Scenario: 服务分支已经一致
- **WHEN** 系统 B 服务当前分支等于目标分支
- **THEN** 构建平台 SHALL 跳过更新并进入 `READY_TO_PUSH`

#### Scenario: 分支修改失败
- **WHEN** 系统 B 更新接口失败或重新查询结果不是目标分支
- **THEN** 构建平台 MUST 标记 `BRANCH_UPDATE_FAILED`，不得开始构建等待或创建打包任务

#### Scenario: 后续构建失败
- **WHEN** 分支切换成功后目标 Pipeline 构建失败
- **THEN** 构建平台 MUST 保留系统 B 当前分支，不得恢复 `previousBranch`

### Requirement: 仅目标 Commit SHA 构建成功可触发打包
构建平台 MUST 使用 GitLab Project ID、branch 和完整 Commit SHA 查找 Pipeline；只有目标 SHA 的 Pipeline 成功才能创建系统 B 自动打包任务。

#### Scenario: 分支存在其他成功 Pipeline
- **WHEN** 分支最新成功 Pipeline 属于其他 Commit SHA
- **THEN** 构建平台 MUST 继续等待目标 Commit SHA，不得触发打包

#### Scenario: 目标 Pipeline 成功
- **WHEN** 目标 Commit SHA 对应 Pipeline 进入成功状态
- **THEN** 构建平台 SHALL 使用 `releaseTaskId` 作为 `clientRequestId` 创建系统 B 自动打包任务

#### Scenario: 目标 Pipeline 失败或超时
- **WHEN** 目标 Pipeline 失败、取消或等待超过期限
- **THEN** 构建平台 SHALL 结束发布任务且不得创建系统 B 自动打包任务

### Requirement: 构建平台精确跟踪系统 B 任务并保存结果快照
构建平台 MUST 保存系统 B 返回的 `packageTaskId` 并仅按该 ID 查询；任务成功时 MUST 将包名称、下载地址、Seafile 地址和 MD5 持久化到本地 SQLite 后停止轮询。

#### Scenario: 自动打包任务成功
- **WHEN** 系统 B 查询返回 `SUCCESS`
- **THEN** 构建平台 SHALL 保存完整制品快照、将发布任务标记为成功并停止查询该 `packageTaskId`

#### Scenario: 系统 B 明确失败
- **WHEN** 系统 B 查询返回失败状态和错误
- **THEN** 构建平台 SHALL 保存失败阶段、错误码和错误消息，并结束当前执行

#### Scenario: 非终态记录已被七天清理
- **WHEN** 构建平台查询中的 `packageTaskId` 已因保留策略不存在
- **THEN** 构建平台 SHALL 将任务标记为 `PACKAGE_RECORD_EXPIRED`，不得猜测其他打包记录

### Requirement: 构建平台支持重启恢复
构建平台 MUST 从 SQLite 恢复未结束的分支更新、构建等待和打包查询任务，并以幂等方式继续当前阶段。

#### Scenario: 分支更新期间重启
- **WHEN** 构建平台重启后发现 `UPDATING_BRANCH` 任务
- **THEN** 构建平台 SHALL 重新查询系统 B 分支，已达目标则推进，否则再次执行同一分支设置

#### Scenario: 打包查询期间重启
- **WHEN** 构建平台重启后发现已保存 `packageTaskId` 的非终态任务
- **THEN** 构建平台 SHALL 恢复按该 ID 查询，不得创建第二个系统 B 任务

