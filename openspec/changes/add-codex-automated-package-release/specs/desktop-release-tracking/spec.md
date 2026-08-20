## ADDED Requirements

### Requirement: 展示真实发布工作流
桌面构建平台 SHALL 展示代码提交、目标确认、系统 B 分支切换、代码推送、GitLab 构建、系统 B 打包、Seafile 上传和发布完成状态，并仅展示后端真实可区分的阶段。

#### Scenario: 正常发布进行中
- **WHEN** 发布任务已完成构建且系统 B 正在打包
- **THEN** 页面 SHALL 将此前阶段显示为完成、打包显示为进行中、后续阶段显示为等待

#### Scenario: 系统 B 只返回合并阶段
- **WHEN** 系统 B 不能分别报告打包和上传进度
- **THEN** 页面 MUST 显示“正在打包并上传 Seafile”的合并阶段，不得虚构两个进度

#### Scenario: 任一阶段失败
- **WHEN** 分支切换、构建、打包或上传失败
- **THEN** 页面 SHALL 标记准确失败阶段并展示稳定错误消息，不得将后续阶段显示为已执行

### Requirement: 发布结果在系统 B 记录清理后仍可查看
桌面构建平台 MUST 使用本地制品快照展示已完成发布的包名称、下载地址、Seafile 地址、MD5、Commit SHA 和 Pipeline 链接，不得依赖系统 B 永久保留任务记录。

#### Scenario: 系统 B 已清理成功任务
- **WHEN** 用户查看超过 7 天的已完成发布且系统 B 任务记录已删除
- **THEN** 页面 SHALL 继续展示本地保存的发布结果，并不得重新轮询系统 B

### Requirement: 通过 Windows Toast 回推发布结果
桌面构建平台 SHALL 在发布成功或失败时发送 Windows Toast；成功通知 MUST 包含服务和版本，并在存在 Seafile 地址时提供打开云盘的点击动作。

#### Scenario: 打包及上传成功
- **WHEN** 构建平台已经持久化系统 B 的成功结果和 Seafile 地址
- **THEN** Windows SHALL 显示一次成功通知，点击通知可打开该 Seafile 地址

#### Scenario: 发布失败
- **WHEN** 发布在分支、构建、打包或上传阶段进入失败终态
- **THEN** Windows SHALL 显示包含失败阶段和简明原因的通知

#### Scenario: 浏览器页面已关闭
- **WHEN** 桌面后台进程仍在运行但工作流页面已经关闭
- **THEN** 发布完成后 Windows Toast 仍 SHALL 正常显示
