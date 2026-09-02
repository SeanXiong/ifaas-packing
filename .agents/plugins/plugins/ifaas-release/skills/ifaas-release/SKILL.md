---
name: ifaas-release
description: "仅当用户显式调用 $ifaas-release 时，为当前 Git 仓库登记 IFAAS 自动打包发布；普通修改、提交、推送、构建或自然语言打包请求均不触发。"
---

# IFAAS 自动发布

仅在本 Skill 被用户显式调用时执行以下流程。调用本 Skill 视为允许准备发布，但不扩大代码提交、外部登记或推送之外的权限。

1. 运行 [scripts/ifaas_release.py](scripts/ifaas_release.py) 读取规范化 Git remote、当前 branch、完整 Commit SHA 和明确打包参数。项目、产品和服务由打包平台固定配置解析，不在 Codex 会话中选择或猜测业务 ID。
2. 构建平台地址与凭据只能由脚本从环境变量、受限本地配置或 Windows Credential Manager 读取，不得写入提示词、命令输出或日志。
3. 完成本地检查和 commit 后，先向构建平台使用稳定 `clientRequestId` 登记发布任务。只有响应包含唯一 `releaseTaskId` 且状态为 `READY_TO_PUSH` 时才允许执行本次发布对应的 `git push`。
4. 登记失败时停止，不得 push。push 失败时调用构建平台失败报告接口，将任务结束为 `PUSH_FAILED`。
5. push 成功后向用户输出 `releaseTaskId` 和等待状态。构建平台负责精确等待目标 Commit Pipeline、创建并轮询打包任务及发送 Windows 通知。

第一阶段使用本地 CLI/HTTP，不依赖 MCP。缺少 Git 上下文、打包参数、构建平台配置或凭据时停止并报告具体缺失项。
