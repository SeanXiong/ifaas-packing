## ADDED Requirements

### Requirement: 打包平台提供自动打包目标设置入口
打包平台 SHALL 在主页面 Header 右上角、用户菜单之前提供自动打包配置状态和“设置”入口，并 SHALL 参考构建平台使用右侧设置抽屉配置自动打包目标。

#### Scenario: 已登录用户打开设置
- **WHEN** 已登录用户点击 Header 的“设置”按钮或自动打包配置状态
- **THEN** 系统 SHALL 打开右侧设置抽屉并展示当前项目、产品及创建和最后修改信息

#### Scenario: 自动打包目标未配置
- **WHEN** 平台不存在有效的自动打包项目和版本配置
- **THEN** Header SHALL 显示“自动打包未配置”，且自动任务创建 SHALL 被阻止

#### Scenario: 已保存配置失效
- **WHEN** 已保存项目或版本已不存在，或版本不再属于该项目
- **THEN** Header SHALL 显示“自动打包配置失效”，并允许用户进入设置重新选择

### Requirement: 项目和产品使用可搜索级联选择
设置抽屉 SHALL 以支持输入匹配的 Combobox 选择项目和产品；产品 SHALL 复用现有版本实体，界面使用“产品”文案，接口和持久化使用 `versionId`。

#### Scenario: 输入关键词搜索项目
- **WHEN** 用户在项目选择框输入关键词
- **THEN** 系统 SHALL 以防抖方式查询真实项目候选，并展示项目名称和 `projectId`

#### Scenario: 输入文本但未选择候选
- **WHEN** 用户只输入任意文本而未从真实候选中选择项目
- **THEN** 系统 MUST 不得把文本作为项目配置保存

#### Scenario: 选择项目后搜索产品
- **WHEN** 用户选择一个真实项目并在产品选择框输入关键词
- **THEN** 系统 SHALL 仅查询该项目下的版本候选，并以产品名称和 `versionId` 展示

#### Scenario: 更换项目
- **WHEN** 用户将已选项目切换为另一个项目
- **THEN** 系统 MUST 清空原产品选择并重新加载新项目下的版本候选

### Requirement: 服务端校验并持久化全局目标配置
打包平台服务端 MUST 在保存前验证项目存在、版本存在且版本属于项目，并 SHALL 将 `projectId`、`versionId`、名称快照及创建和最后修改信息保存为全局自动打包配置。

#### Scenario: 首次保存有效配置
- **WHEN** 已登录用户首次提交有效 `projectId` 和 `versionId`
- **THEN** 系统 SHALL 同时记录 `createdBy`、`createdAt`、`updatedBy` 和 `updatedAt`

#### Scenario: 修改已有配置
- **WHEN** 已登录用户保存新的有效项目和版本
- **THEN** 系统 SHALL 保留原 `createdBy` 和 `createdAt`，并更新 `updatedBy` 和 `updatedAt`

#### Scenario: 版本不属于项目
- **WHEN** 用户提交的 `versionId` 不属于所提交的 `projectId`
- **THEN** 系统 MUST 拒绝保存并返回稳定的配置校验错误

### Requirement: 自动任务固化配置快照
每个自动打包任务 MUST 在创建时保存所用项目和版本的 ID 与名称快照，后续全局设置修改 MUST 不得改变已创建或排队任务的目标。

#### Scenario: 任务创建后修改设置
- **WHEN** 自动任务已使用项目 A 和版本 A 创建，随后用户把全局设置改为项目 B 和版本 B
- **THEN** 已创建任务 SHALL 继续使用项目 A 和版本 A，新任务 SHALL 使用项目 B 和版本 B
