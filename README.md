# IFAAS 项目打包工具

一个轻量级 HTML 单页打包工具，通过本地 Python 标准库服务器运行。

## 功能

- 登录后自动保存 Token，用于后续接口请求。
- 左侧支持项目名称实时搜索、收藏项目、收藏持久化。
- 中间按项目加载版本。
- 右侧按版本加载组件，支持全选、局部过滤、组件勾选。
- 支持离线/在线升级包、CPU 架构、命名空间配置。
- 支持按服务获取 Git 分支并修改当前服务分支。
- 点击"开始打包"后按接口规范提交 JSON。
- 支持查看升级包记录、复制下载地址、上传网盘。

## 启动方式

零额外依赖，Python 3 标准库即可：

```bash
python server.py
```

浏览器打开 `http://127.0.0.1:8080`，登录后即可使用。

## 配置文件

所有配置以 JSON 文件保存在 `config/` 目录：

| 文件 | 用途 |
|------|------|
| `config/server.json` | 后端 API 地址和监听端口 |
| `config/favorites.json` | 收藏的项目 ID 列表 |
| `config/credentials.json` | 记住的登录凭据 |

## 接口配置

后端地址修改：编辑 `config/server.json` 中的 `backend_url` 字段。

## 项目结构

```
ifaas-packing/
├── server.py                  # 极简本地服务器（Python 标准库）
├── web/                       # HTML 前端
│   ├── index.html             # 单页应用
│   ├── css/app.css            # 样式
│   └── js/
│       ├── api.js             # API 客户端
│       ├── config.js          # 配置读写
│       ├── app.js             # 主应用逻辑
│       └── utils.js           # 工具函数
├── config/                    # 运行时配置文件
│   ├── server.json
│   ├── favorites.json
│   └── credentials.json
└── README.md
```
