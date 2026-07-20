## ADDED Requirements

### Requirement: 按打包类型查询记录
系统 SHALL 在打包记录弹窗中提供打包类型筛选，选项为离线升级包、在线升级包、离线安装包和在线安装包，默认选中离线升级包。

#### Scenario: 默认查询离线升级包
- **WHEN** 用户打开某个版本的打包记录弹窗
- **THEN** 系统 SHALL 请求 `/api/v1/recordsprojectupdate/`，并携带该版本 ID 与 `offline_status=True`

#### Scenario: 查询在线安装包
- **WHEN** 用户将打包类型切换为在线安装包
- **THEN** 系统 SHALL 请求 `/api/v1/recordsprojectinstall/`，并携带该版本 ID 与 `offline_status=False`

### Requirement: 记录列表不提供已移除的本地过滤控件
记录弹窗 MUST 不展示搜索框、状态筛选、CPU 架构筛选或优先级排序控件，并 SHALL 按后端返回顺序展示记录。

#### Scenario: 展示选中类型的记录
- **WHEN** 记录查询成功返回多条记录
- **THEN** 系统 SHALL 按响应中的记录顺序渲染全部记录

### Requirement: 按包族删除记录
系统 SHALL 根据记录所属包族删除记录；升级包使用 `/api/v1/recordsprojectupdate/{recordId}`，安装包使用 `/api/v1/recordsprojectinstall/{recordId}`。

#### Scenario: 删除安装包记录
- **WHEN** 用户确认删除一条安装包记录
- **THEN** 系统 SHALL 向 `/api/v1/recordsprojectinstall/{recordId}` 发送 DELETE 请求，并在成功后从当前列表移除该记录
