## ADDED Requirements

### Requirement: 自动任务在固定版本中唯一定位服务
打包平台 MUST 读取有效的全局项目与版本配置，并使用规范化 `repositoryUrl` 与该版本服务 `git_url` 精确匹配目标服务；服务名称语义相似度 MUST 不得替代 Git URL 匹配。

#### Scenario: 唯一服务匹配
- **WHEN** 配置版本中恰有一个服务的规范化 Git URL 与请求仓库一致
- **THEN** 系统 SHALL 固化该项目、版本、服务和 Git 信息并继续自动任务

#### Scenario: 没有匹配服务
- **WHEN** 配置版本中不存在匹配当前仓库的服务
- **THEN** 系统 MUST 以 `SERVICE_NOT_FOUND` 结束任务且不得猜测其他服务

#### Scenario: 存在多个匹配服务
- **WHEN** 配置版本中存在多个匹配当前仓库的服务
- **THEN** 系统 MUST 以 `SERVICE_TARGET_AMBIGUOUS` 结束任务且不得默认选择第一个服务

### Requirement: 自动打包任务异步创建并保持幂等
打包平台 SHALL 提供异步自动任务创建和按 `packageTaskId` 精确查询能力；创建请求 MUST 使用 `clientRequestId` 持久化幂等，重复请求不得创建第二个包。

#### Scenario: 首次创建任务
- **WHEN** 调用方提交有效目标分支和打包参数
- **THEN** 系统 SHALL 原子保存任务并返回唯一 `packageTaskId` 和 `202 Accepted`

#### Scenario: 创建响应丢失后重试
- **WHEN** 调用方以相同 `clientRequestId` 重复提交创建请求
- **THEN** 系统 SHALL 返回原 `packageTaskId` 且不得重复排队或打包

#### Scenario: 服务重启恢复任务
- **WHEN** 打包平台重启后存在非终态任务
- **THEN** 系统 SHALL 从持久化阶段幂等恢复，且不得重复创建打包或补偿上传

### Requirement: 同一版本服务任务持久化排队并独占执行
打包平台 MUST 以 `versionId:serviceId` 为锁键对任务进行持久化 FIFO 排队，并 MUST 防止同一锁键的两个任务同时执行会读取或修改服务分支的阶段。

#### Scenario: 同一服务已有运行任务
- **WHEN** 新任务与运行任务具有相同 `versionId:serviceId`
- **THEN** 新任务 SHALL 进入 `QUEUED` 并返回真实队列位置，不得并行切换分支或生成包

#### Scenario: 前序任务释放锁
- **WHEN** 前序任务完成最后一次依赖服务分支的操作并释放锁
- **THEN** 队列中最早的任务 SHALL 获得锁并继续执行

#### Scenario: 持锁期间进程重启
- **WHEN** 打包平台重启时存在持锁任务和同键排队任务
- **THEN** 系统 MUST 恢复唯一锁所有者并保持原 FIFO 顺序，不得并行恢复同键任务

### Requirement: 打包平台自动校准服务分支
持锁任务 MUST 验证目标 branch 存在，并在服务配置分支不一致时读取完整服务和目标 Git 配置、提交完整更新且重新查询验证；任务结束后 MUST 不得自动恢复原分支。

#### Scenario: 服务分支已经一致
- **WHEN** 服务当前配置分支等于请求目标分支
- **THEN** 系统 SHALL 跳过更新并记录 `changed=false` 和 `verified=true`

#### Scenario: 服务分支需要切换
- **WHEN** 服务当前配置分支与请求目标分支不同且目标 branch 存在有效 `git_id`
- **THEN** 系统 SHALL 更新并重新验证服务分支，记录原分支、目标分支和 `changed=true`

#### Scenario: 分支校准失败
- **WHEN** 目标分支不存在、缺少 Git 配置或更新后验证不一致
- **THEN** 系统 MUST 以 `BRANCH_ALIGNMENT_FAILED` 结束任务且不得开始打包

### Requirement: 组合打包上传缺少地址时执行一次补偿
当 `uploadCloud=true` 时，打包平台 MUST 在原打包请求中启用现有云盘上传选项；组合任务完成后 MUST 检查真实云盘地址，确认不存在进行中上传且地址缺失时 SHALL 触发一次幂等补偿上传。

#### Scenario: 组合任务已返回云盘地址
- **WHEN** 打包完成且记录包含可用 `cloudUrl` 或 `cloudPath`
- **THEN** 系统 SHALL 直接完成任务且不得再次调用独立上传

#### Scenario: 云盘上传仍在进行
- **WHEN** 包已生成、地址暂缺但存在进行中的上传任务
- **THEN** 系统 SHALL 继续查询现有上传且不得创建补偿上传

#### Scenario: 确认缺少云盘地址
- **WHEN** 包已生成、没有进行中上传且云盘地址仍为空
- **THEN** 系统 SHALL 使用 `packageTaskId:cloud-recovery` 幂等触发一次现有独立上传能力

#### Scenario: 补偿后仍缺少地址
- **WHEN** 补偿上传终止后仍不存在可用云盘地址
- **THEN** 系统 MUST 以 `CLOUD_ADDRESS_MISSING` 结束任务且不得无限重试

### Requirement: 自动任务返回完整可审计结果
自动任务查询 MUST 返回真实状态、阶段、目标快照、队列信息、分支校准、包信息、云盘路径、云盘链接和结构化错误；`uploadCloud=true` 时仅在存在可用云盘地址后才能成功。

#### Scenario: 要求上传云盘的任务成功
- **WHEN** 包生成成功且最终存在可用云盘路径或链接
- **THEN** 系统 SHALL 返回 `SUCCESS`、包名称、下载地址、云盘结果、MD5 和补偿标记

#### Scenario: 不要求上传云盘的任务成功
- **WHEN** `uploadCloud=false` 且包生成成功
- **THEN** 系统 SHALL 在不要求云盘地址的情况下返回 `SUCCESS`
