# 打包平台开发约束

## Python 版本兼容性

- 打包平台主运行链路必须兼容 Python 3.6.9，包括 Web 服务、命令行工具、自动打包任务和发布脚本。
- 不得使用 Python 3.7 及以上版本才支持的语法、标准库 API 或运行时行为。
- 新增或升级主运行链路依赖时，必须确认该依赖支持 Python 3.6.9，并显式约束兼容版本。
- 修改 Python 代码后，必须运行 `python -m unittest discover -s tests -v`，确保 `tests/test_python36_compatibility.py` 通过。
- 可选 MCP 入口使用独立依赖和版本约束，不属于 Python 3.6.9 兼容范围；不得让其依赖进入打包平台主运行链路。
