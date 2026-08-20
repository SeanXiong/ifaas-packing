## ADDED Requirements

### Requirement: 创建唯一且幂等的自动打包任务
系统 B MUST 提供异步自动打包创建接口，在接受有效请求时生成全局唯一 `taskId`，并在返回前持久化任务；在记录保留期内，相同 `clientRequestId` MUST 返回原 `taskId` 且不得重复执行打包。

#### Scenario: 首次创建自动打包任务
- **WHEN** 构建平台提交有效项目、版本、服务、包类型、CPU、namespace 和 Seafile 参数
- **THEN** 系统 B SHALL 返回 `202 Accepted`、唯一 `taskId` 和初始状态，并在后台执行打包

#### Scenario: 创建响应丢失后重试
- **WHEN** 构建平台使用相同 `clientRequestId` 重复提交创建请求
- **THEN** 系统 B MUST 返回第一次创建的 `taskId`，且只存在一次打包执行

### Requirement: 自动打包任务使用本地文件可靠持久化
系统 B SHALL 使用现有本地文件体系保存自动任务的请求快照、状态、阶段、进度、制品、错误和时间；每次更新 MUST 通过同目录临时文件完整写入后原子替换目标记录。

#### Scenario: 创建记录后进程退出
- **WHEN** 系统 B 已返回 `taskId` 后进程意外退出
- **THEN** 重启后系统 B SHALL 能按该 `taskId` 查询记录，并恢复或明确标记未完成任务

#### Scenario: 更新记录期间中断
- **WHEN** 进程在写入任务新状态时中断
- **THEN** 查询接口 MUST 不返回半写入或无法解析的 JSON 记录

### Requirement: 按 taskId 精确查询打包和上传结果
系统 B MUST 提供按 `taskId` 查询单条任务的接口，并返回稳定的任务状态、实际可用阶段、进度、制品、Seafile 地址、MD5 和结构化错误。

#### Scenario: 打包正在执行
- **WHEN** 构建平台查询处于打包阶段的 `taskId`
- **THEN** 系统 B SHALL 返回非终态状态和真实可用的打包进度，不得返回其他记录的结果

#### Scenario: Seafile 上传完成
- **WHEN** 系统 B 已完成打包和 Seafile 上传
- **THEN** 查询接口 SHALL 返回 `SUCCESS`，并包含包名称、下载地址、Seafile 地址和 MD5

#### Scenario: 后端不能区分打包与上传阶段
- **WHEN** 系统 B 只能提供合并进度
- **THEN** 查询接口 SHALL 返回合并的运行阶段，不得虚构独立上传进度

### Requirement: 系统 B 自行完成 Seafile 上传
当 `uploadCloud=true` 时，系统 B MUST 在打包任务中调用既有 Seafile 能力并将云盘地址写入同一任务结果；构建平台不得直接上传制品。

#### Scenario: 上传成功
- **WHEN** 离线包制作完成且请求要求上传云盘
- **THEN** 系统 B SHALL 完成 Seafile 上传后再将任务标记为 `SUCCESS`

#### Scenario: 上传失败
- **WHEN** Seafile 最终上传失败
- **THEN** 系统 B SHALL 将任务标记为失败并返回上传阶段、稳定错误码和错误消息

### Requirement: 清理超过七天的全部自动任务状态
系统 B MUST 在启动后及此后每 24 小时清理 `createdTime` 早于当前时间 7 天的全部自动打包记录，不得按状态排除任务。

#### Scenario: 清理七天前的成功任务
- **WHEN** 自动任务创建时间超过 7 天且状态为 `SUCCESS`
- **THEN** 系统 B SHALL 删除任务记录、进度数据和对应幂等映射，但不得删除 Seafile 文件

#### Scenario: 清理七天前的执行中任务
- **WHEN** 自动任务创建时间超过 7 天且状态为 `PACKAGING` 或 `UPLOADING`
- **THEN** 系统 B SHALL 停止该任务、阻止后台工作重新写回记录，并删除任务记录及幂等映射

#### Scenario: 保留手工打包记录
- **WHEN** 手工打包记录创建时间超过 7 天
- **THEN** 自动任务清理器 MUST 不删除该记录

