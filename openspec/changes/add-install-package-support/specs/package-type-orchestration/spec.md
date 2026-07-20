## ADDED Requirements

### Requirement: 选择并确认四类打包类型
系统 SHALL 在用户点击“开始打包”后提供升级包和安装包的包族选择，并与当前离线/在线选择组合为离线升级包、在线升级包、离线安装包或在线安装包。

#### Scenario: 选择安装包并进入二次确认
- **WHEN** 用户在开始打包后的包族选择弹窗中选择安装包
- **THEN** 系统 SHALL 打开组件与分支二次确认弹窗，并显示当前联网方式对应的完整安装包类型

#### Scenario: 取消包族选择
- **WHEN** 用户在包族选择弹窗中取消操作
- **THEN** 系统 MUST 不创建打包请求，且保留当前组件选择和右侧配置

### Requirement: 按最终包类型提交打包请求
系统 SHALL 按最终包类型提交打包请求；升级包使用 `/api/v1/packplus/upgrade/{versionId}`，安装包使用 `/api/v1/packplus/install/{versionId}`，并在请求体中传递与界面离线/在线选择一致的 `offline` 值。

#### Scenario: 提交离线安装包
- **WHEN** 用户确认离线安装包打包
- **THEN** 系统 SHALL 向 `/api/v1/packplus/install/{versionId}` 提交 `offline: 1` 的打包请求

#### Scenario: 提交在线升级包
- **WHEN** 用户确认在线升级包打包
- **THEN** 系统 SHALL 向 `/api/v1/packplus/upgrade/{versionId}` 提交 `offline: 0` 的打包请求

### Requirement: 安装包请求可长时间等待
本地代理 MUST 将 `/api/v1/packplus/install/` 作为长请求路径，与升级包提交使用相同的无固定超时策略。

#### Scenario: 安装包提交超过默认代理等待时间
- **WHEN** 安装包提交的后端响应时间超过普通代理请求的默认超时时间
- **THEN** 本地代理 MUST 继续等待后端响应而非以默认超时失败
