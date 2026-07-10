# 会话 Token 自动登录实施计划

> **面向执行代理：** 必须逐项执行并验证。

**目标：** 在当前浏览器标签页缓存登录 Token，刷新后自动进入业务页；认证失效时提示并回到登录页。

**架构：** `SessionStore` 负责访问 `sessionStorage`。`ApiClient` 保存和清除 Token，并将认证失败转换为可识别错误。页面启动时恢复 Token 并加载项目；认证错误统一清除会话、提示和显示登录页。

**技术栈：** 原生 JavaScript、浏览器 `sessionStorage`、Node.js 断言测试。

## 任务一：会话 Token 与认证错误

**文件：**

- 修改：`web/js/api.js`
- 测试：`web/js/api.test.js`

- [ ] 增加失败测试：`401` 响应被标识为认证失效。
- [ ] 增加 `setToken`、`clearToken` 和 `isAuthenticationError`，并在 `_request` 中保留 HTTP 状态。
- [ ] 测试认证错误识别和现有分页逻辑。

## 任务二：启动恢复与失效跳转

**文件：**

- 修改：`web/js/app.js`
- 修改：`web/js/app.test.js`

- [ ] 增加失败测试：缓存 Token 启动时直接进入主页面；认证失效时清除缓存并提示。
- [ ] 实现 `sessionStorage` 的 Token 读写、自动恢复登录态和统一认证失效处理。
- [ ] 在普通登录成功后写入缓存；所有业务接口失败时仅认证错误跳转登录。
- [ ] 运行全部 JavaScript 测试和语法检查。
