## 非生产环境契约盘点

盘点日期：2026-09-02。

盘点范围：

- 打包平台：`http://192.168.14.91:36001/`
- 构建平台：`http://127.0.0.1:8765/`
- 打包平台账号通过本地 profile 读取；本文不记录账号、密码或 Token。
- 只执行页面资源读取、GET 查询，以及语义只读的 refs POST；未创建打包或发布任务，未修改服务分支，未触发上传。

## 已确认入口

| 能力 | 方法与路径 | 本次确认结果 |
|---|---|---|
| 项目分页搜索 | `GET /api/v1/project/?page={page}&pageSize={pageSize}&name={query}` | 返回分页项目列表 |
| 单项目查询 | `GET /api/v1/project/{projectId}` | 已由共享客户端封装 |
| 项目版本 | `GET /api/v1/version/?project_id={projectId}` | 返回版本列表 |
| 版本服务 | `GET /api/v1/module/?version_id={versionId}&git_tag=True` | 返回服务、当前分支和 Git 配置 |
| Git refs | `POST /api/v1/refs/` | 请求体为 `git_url`，返回 branches 和 tags |
| Git 配置 | `POST /api/v1/git_config/` | 已由部署前端确认请求结构；本次未额外调用 |
| 模块更新 | `PUT /api/v1/module/{serviceId}` | 已由部署前端确认入口；本次未执行修改 |
| 升级包提交 | `POST /api/v1/packplus/upgrade/{versionId}` | 已由部署前端确认入口；本次未创建包 |
| 安装包提交 | `POST /api/v1/packplus/install/{versionId}` | 已由部署前端确认入口；本次未创建包 |
| 升级包记录 | `GET /api/v1/recordsprojectupdate/` | 已取得在线、离线真实样例 |
| 安装包记录 | `GET /api/v1/recordsprojectinstall/` | 已取得离线真实样例 |
| 独立 Seafile 上传 | `POST /api/v1/package/2seafile` | 请求体字段为 `storagePath`；本次未触发 |
| 上传进度 | `GET /api/v1/package/progress/{taskId}?task_id={taskId}` | 已取得真实历史任务响应 |
| 自动任务查询 | `GET /api/v1/automation/package-tasks/{packageTaskId}` | 当前部署返回 HTTP 404，尚未交付 |
| 构建平台发布任务 | `GET/POST /api/release-tasks` | OPTIONS 确认 GET、POST；当前列表为空 |

## 真实响应样例

以下样例保留真实字段结构，名称、地址、账号和制品路径均已脱敏。

### 项目分页

```json
{
  "projects": [{"projectId": 586, "name": "<已脱敏项目名>", "description": ""}],
  "page": 1,
  "pageSize": 10,
  "total": 31
}
```

### 项目版本

```json
{
  "versions": [{"versionId": 2416, "name": "rel_2.0.2_deepsea", "enabled": true}]
}
```

### 版本服务

```json
{
  "services": [{
    "serviceId": 33417,
    "name": "ifaas-authority",
    "customName": "ifaas-authority",
    "branch": "<已脱敏分支>",
    "gitUrl": "http://<gitlab>/<group>/ifaas-authority.git",
    "gitId": 446,
    "serviceType": 1
  }]
}
```

真实版本中可能有多个服务共享同一规范化 Git URL，因此自动任务必须检测多匹配，不能默认使用首个服务。

### Git refs

```json
{
  "branches": ["develop", "<已脱敏分支>"],
  "tags": ["<已脱敏标签>"]
}
```

### 打包记录

四类记录使用相同核心字段。真实离线升级包样例如下：

```json
{
  "id": 32821,
  "version": {"id": 2416, "update_version": "rel_2.0.2_deepsea", "project": 586},
  "offline_status": true,
  "pack_status": "<后端状态>",
  "download_path": "http://<artifact-host>/<已脱敏制品路径>",
  "storage_path": "/tmp/<已脱敏制品路径>",
  "fileMD5": "862a910e9a30236001ba7387dcabd6c3",
  "seafile_path": "https://<seafile-host>/<已脱敏云盘路径>",
  "task_id_2seafile": "7131946a-af63-446a-a30b-48e219103d2f"
}
```

### 上传进度

```json
{
  "state": "PENDING",
  "complete": false,
  "success": null,
  "progress": {"pending": true, "current": 0, "total": 100, "percent": 0}
}
```

该历史记录已经存在有效 `seafile_path`，对应进度仍返回 `PENDING`。因此最终云盘成功判断必须以重新查询打包记录得到的 `seafile_path` 为主要依据；进度接口只用于判断已知上传任务是否仍在运行，不能覆盖已经存在的云盘地址。

## 字段白名单

### 项目

- `projectId`
- `name`
- `description`

### 版本

- `versionId`
- `name`
- `enabled`

### 服务

- `serviceId`
- `name`
- `customName`
- `branch`
- `gitUrl`
- `gitId`
- `serviceType`

### refs

- `branches`
- `tags`

### 打包记录与制品

- `id`
- `version.id`
- `version.update_version`
- `version.project`
- `offline_status`
- `pack_status`
- `download_path`
- `storage_path`
- `fileMD5`
- `seafile_path`
- `task_id_2seafile`
- `created_time`
- `updated_time`

### 上传进度

- `state`
- `complete`
- `success`
- `progress.pending`
- `progress.current`
- `progress.total`
- `progress.percent`
- `progress.description`
- `progress.elapsed`
- `progress.speed`

## 尚未确认

- 真实后端 Service、文件记录、组合打包上传和独立上传的代码入口。
- 打包引擎最后一次读取服务分支的时点，以及锁应在包生成还是组合上传结束后释放。
- `pack_status` 的完整枚举及组合上传进行中状态与 `task_id_2seafile` 的关联规则。
- 构建平台 `POST /api/release-tasks` 的当前旧版请求结构不作为新 change 契约；新契约以 `contracts/release-task.schema.json` 为准。

## 第一阶段实施决定

根据产品方确认，第一阶段直接兼容当前部署页面的现有调用逻辑，其余枚举和关联规则暂不作为交付前置条件：

- 以 `download_path` 或 `storage_path` 出现作为制品记录可用依据。
- 以 `seafile_path` 出现作为云盘结果可用依据。
- 有 `task_id_2seafile` 且进度未完成时仅等待；无进行中任务时才执行一次本地幂等补偿。
- 服务锁保守持有到打包请求返回并查询到新增制品记录。
