# IFAAS 项目打包桌面客户端

一个替代网页端的 PyQt6 单窗口三栏联动打包工具。

## 功能

- 启动后自动登录并保存 Token 到进程内，用于后续接口请求。
- 左侧支持项目名称实时搜索、收藏项目、收藏持久化。
- 中间按项目加载版本。
- 右侧按版本加载组件，支持全选、局部过滤、组件勾选。
- 支持离线/在线升级包、CPU 架构、命名空间配置。
- 支持按服务获取 Git 分支并修改当前服务分支。
- 点击“开始打包”后按接口规范提交 JSON。

## 安装与启动

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 收藏数据

收藏项目 ID 默认保存到：

```text
%USERPROFILE%\.ifaas_packing\favorites.json
```

## 接口配置

当前接口地址和默认登录账号位于：

- `ifaas_packing/api.py`

如需改成配置文件或登录页，可以继续在该模块上扩展。
