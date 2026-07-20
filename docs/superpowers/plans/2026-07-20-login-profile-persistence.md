# 登录账号本地保存实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 登录认证成功后将账号密码按登录名写入 `config/login-profiles.json`，供 `?profile=<登录名>` 预填使用。

**Architecture:** `ConfigStore.saveLoginProfile` 读取现有账号集合、覆盖当前登录名并写回配置。`doLogin` 在建立会话后调用该方法；配置写入异常只提示，不影响登录成功后的业务页面加载。

**Tech Stack:** 原生 JavaScript、Node 内置断言测试、Python 标准库配置接口。

## 全局约束

- 密码不写入 URL、日志或提示文本。
- 同名登录覆盖原有密码。
- 配置写入失败不阻断登录。

---

### 任务 1：保存配置能力

**文件：**
- 修改：`web/js/config.test.js`
- 修改：`web/js/config.js`

- [ ] 编写断言：保存账号后 `accounts.<用户名>` 含用户名和密码，重复保存覆盖旧密码。
- [ ] 运行 `node web/js/config.test.js`，预期因缺少 `saveLoginProfile` 失败。
- [ ] 实现 `ConfigStore.saveLoginProfile(username, password)`，保留其他账号数据并覆盖当前账号。
- [ ] 运行 `node web/js/config.test.js`，预期通过。

### 任务 2：登录成功后保存

**文件：**
- 修改：`web/js/app.test.js`
- 修改：`web/js/app.js`

- [ ] 编写断言：认证成功后调用 `ConfigStore.saveLoginProfile`，保存失败仍进入业务页面。
- [ ] 运行 `node web/js/app.test.js`，预期因未调用保存方法失败。
- [ ] 在 `doLogin` 中于认证成功后异步保存账号密码；写入异常仅显示账号信息未保存提示。
- [ ] 运行 `node web/js/app.test.js`，预期通过。

### 任务 3：验证与缓存更新

**文件：**
- 修改：`web/index.html`
- 修改：`web/js/app.test.js`

- [ ] 更新缓存版本断言并先验证失败。
- [ ] 更新静态资源查询版本。
- [ ] 运行 `node web/js/app.test.js`、`node web/js/config.test.js`、`node web/js/api.test.js`、`node --check web/js/app.js`、`node --check web/js/config.js`、`python server.test.py` 和 `git diff --check`，预期全部通过。
