## ADDED Requirements

### Requirement: 构建平台持久化精确发布任务
构建平台 MUST 按 `clientRequestId` 幂等保存仓库、GitLab Project、branch、`packageTrigger`、`packageTargets` 和打包参数。`AFTER_PIPELINE` 还 MUST 保存完整 Commit SHA，并在持久化完成后返回唯一 `releaseTaskId` 和 `READY_TO_PUSH`；`DIRECT` SHALL 以 `CREATING_PACKAGE` 落库并立即下发打包。

#### Scenario: 首次登记发布任务
- **WHEN** Skill 提交完整有效的发布请求
- **THEN** 构建平台 SHALL 原子保存请求快照并开始等待目标 Commit Pipeline

#### Scenario: 重复登记同一请求
- **WHEN** Skill 使用相同 `clientRequestId` 重试登记
- **THEN** 构建平台 SHALL 返回原 `releaseTaskId` 且不得创建第二条发布工作流

### Requirement: 仅目标 Commit 构建成功触发打包
`AFTER_PIPELINE` 模式下，构建平台 MUST 使用 GitLab Project、branch 和完整 Commit SHA 查找 Pipeline；其他 Commit 的成功 Pipeline MUST 不得触发当前发布任务。`DIRECT` 模式 MUST 跳过 Pipeline 查询，并把全部 `packageTargets` 直接转换为打包平台 `targets`。

#### Scenario: 直接创建融合打包任务
- **WHEN** 发布任务使用 `DIRECT` 并包含多个 `packageTargets`
- **THEN** 构建平台 SHALL 在任务落库后只创建一次打包任务，并完整传递所有目标服务

#### Scenario: 目标 Commit 构建成功
- **WHEN** 目标 Commit SHA 对应 Pipeline 进入成功状态
- **THEN** 构建平台 SHALL 使用 `releaseTaskId` 作为 `clientRequestId` 创建打包平台自动任务

#### Scenario: 分支存在其他成功构建
- **WHEN** branch 上存在成功 Pipeline 但其 Commit SHA 与发布任务不同
- **THEN** 构建平台 MUST 继续等待目标 Commit 且不得创建打包任务

#### Scenario: 目标构建失败或超时
- **WHEN** 目标 Pipeline 失败、取消或超过配置期限
- **THEN** 构建平台 SHALL 结束发布任务并不得调用打包平台

### Requirement: 构建平台按任务 ID 跟踪打包结果
构建平台 MUST 保存打包平台返回的 `packageTaskId` 并仅按该 ID 有界轮询；网络重试 MUST 复用相同幂等键，不得重复创建包。

#### Scenario: 打包任务排队或运行
- **WHEN** 打包平台返回 `QUEUED` 或其他非终态阶段
- **THEN** 构建平台 SHALL 保存真实阶段和队列信息并继续查询同一 `packageTaskId`

#### Scenario: 构建平台重启
- **WHEN** 构建平台重启后发现已保存 `packageTaskId` 的非终态发布任务
- **THEN** 构建平台 SHALL 恢复查询原任务且不得再次创建打包任务

### Requirement: 构建平台保存制品结果
打包任务终止时，构建平台 MUST 保存解析目标、分支变化、包名称、下载地址、云盘路径、云盘链接、MD5 和错误快照；终态展示 MUST 不依赖打包平台永久保留记录。

#### Scenario: 打包成功
- **WHEN** 打包平台返回 `SUCCESS`
- **THEN** 构建平台 SHALL 保存结果并把发布任务标记为成功

#### Scenario: 打包失败
- **WHEN** 打包平台返回结构化失败阶段、错误码和消息
- **THEN** 构建平台 SHALL 保存错误快照并以对应阶段结束发布任务

### Requirement: Windows 通知准确反映最终结果
构建平台 SHALL 在发布成功或失败时发送一次 Windows Toast；通知失败 SHALL 独立记录且不得改变已完成发布的主状态。

#### Scenario: 成功且存在云盘链接
- **WHEN** 构建平台已保存成功结果和 `cloudUrl`
- **THEN** Windows 通知 SHALL 包含服务、产品和云盘结果，并支持点击打开云盘链接

#### Scenario: 发布失败
- **WHEN** 构建、服务发现、分支校准、打包或云盘上传进入失败终态
- **THEN** Windows 通知 SHALL 展示准确失败阶段和简明原因
