## ADDED Requirements

### Requirement: 在线包禁止云盘上传
系统 MUST 对在线升级包和在线安装包禁用云盘上传：右侧云盘开关必须取消选中并不可操作，提交请求中的 `seafile` 必须为 `false`，记录卡片不得展示上传云盘操作。

#### Scenario: 切换为在线包配置
- **WHEN** 用户在右侧配置中选择在线方式
- **THEN** 系统 SHALL 取消选中并禁用云盘上传开关

#### Scenario: 查看在线包记录
- **WHEN** 用户查看在线升级包或在线安装包记录且记录没有云盘地址
- **THEN** 系统 MUST 不显示上传云盘按钮

### Requirement: 离线包支持云盘上传
系统 SHALL 允许离线升级包和离线安装包在没有云盘地址时发起云盘上传，并使用 `/api/v1/package/2seafile` 与记录的 `storage_path` 创建上传任务。

#### Scenario: 上传离线安装包
- **WHEN** 用户对没有云盘地址的离线安装包记录点击上传云盘
- **THEN** 系统 SHALL 使用该记录的 `storage_path` 创建上传任务

### Requirement: 展示上传速度
系统 SHALL 在云盘上传进行中显示进度百分比；当进度响应包含 `progress.speed` 时，系统 MUST 同时展示该上传速度。

#### Scenario: 进度响应包含速度
- **WHEN** 云盘上传进度接口返回未完成任务，且 `progress.percent` 为 `5.3`、`progress.speed` 为 `67.09 MB/s`
- **THEN** 上传进度区域 SHALL 显示 `5.3%` 和 `67.09 MB/s`

#### Scenario: 上传完成
- **WHEN** 云盘上传进度接口返回 `complete: true` 且 `success: true`
- **THEN** 系统 SHALL 显示上传完成状态，并重新查询当前选中的打包类型记录
