# 打包参数弹窗实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将打包类型、网络、CPU、命名空间和云盘上传统一到开始打包后的表单弹窗，并固定组件配置中心参数。

**Architecture:** `buildPackPayload` 只收集已选模块并固定 `need_apollo`；新的参数弹窗将表单值合并进载荷，再传给既有确认弹窗和提交 API。右侧页面移除一次性打包参数控件。

**Tech Stack:** 原生 HTML、CSS、JavaScript、Node 内置断言测试。

## 全局约束

- 默认值为安装包、离线、`x86_64`、`basic-app`、不上传云盘。
- 在线包不支持上传云盘。
- 所有模块固定提交 `need_apollo: true`。

---

### 任务 1：参数弹窗与载荷构建

**文件：**
- 修改：`web/js/app.test.js`
- 修改：`web/js/app.js`

- [ ] 编写断言，验证默认参数载荷、在线禁用云盘以及模块 `need_apollo: true`。
- [ ] 运行 `node web/js/app.test.js`，预期因现有右侧控件依赖而失败。
- [ ] 将 `showPackageFamilySelection` 替换为表单式参数弹窗；从弹窗表单生成 `packageType`、`offline`、`support_cpu`、`namespace`、`seafile`。
- [ ] 将 `buildPackPayload` 改为仅构建模块，模块固定为 `need_apollo: true`。
- [ ] 运行 `node web/js/app.test.js`，预期通过。

### 任务 2：右侧页面清理与确认信息

**文件：**
- 修改：`web/index.html`
- 修改：`web/js/app.js`
- 修改：`web/js/app.test.js`

- [ ] 编写断言，验证右侧页面不再包含网络、CPU、Apollo、命名空间和云盘控件，并验证确认弹窗包含参数标签。
- [ ] 运行 `node web/js/app.test.js`，预期失败。
- [ ] 移除右侧全局参数区域，并在二次确认弹窗展示包类型、网络类型、CPU 架构、命名空间和云盘上传状态。
- [ ] 删除已失效的右侧网络类型与云盘同步事件。
- [ ] 运行 `node web/js/app.test.js`，预期通过。

### 任务 3：完整验证

**文件：**
- 修改：`web/index.html`
- 修改：`web/js/app.test.js`

- [ ] 更新静态资源缓存版本并使缓存版本断言先失败。
- [ ] 运行 `node web/js/app.test.js`，预期失败。
- [ ] 更新 `web/index.html` 的 CSS 与 JavaScript 查询版本号。
- [ ] 运行 `node web/js/app.test.js`、`node web/js/config.test.js`、`node web/js/api.test.js`、`node --check web/js/app.js`、`python server.test.py` 和 `git diff --check`，预期均通过。
