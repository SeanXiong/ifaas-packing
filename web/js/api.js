/**
 * ifaas-packing API 客户端（对应原 api.py 的 ApiClient）
 * 所有请求通过 server.py 代理转发，解决浏览器 CORS 限制
 */

const ApiClient = {
    token: null,
    username: '',
    password: '',
    onAuthenticationFailure: null,

    init(username, password) {
        this.username = username;
        this.password = password;
        this.token = null;
    },

    /** 通过代理发送 HTTP 请求 */
    async _request(method, path, body = null) {
        const url = `/api/proxy${path}`;
        const headers = { 'Content-Type': 'application/json' };
        if (this.token) {
            headers['Authorization'] = `Token ${this.token}`;
        }

        const opts = { method, headers };
        if (body !== null) {
            opts.body = JSON.stringify(body);
        }

        const resp = await fetch(url, opts);
        const text = await resp.text();
        let data = null;
        if (text) {
            try {
                data = JSON.parse(text);
            } catch {
                data = text;
            }
        }

        const detail = data && typeof data === 'object'
            ? (data.detail || data.message || JSON.stringify(data))
            : String(data || resp.statusText || '请求失败');
        if (this.isAuthenticationFailure(resp.status, data)) {
            const error = new Error(detail || '登录状态已失效。');
            error.isAuthenticationError = true;
            if (typeof this.onAuthenticationFailure === 'function') {
                this.onAuthenticationFailure(error);
            }
            throw error;
        }
        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}: ${detail}`);
        }
        return data;
    },

    isAuthenticationFailure(status, data) {
        if (status === 401 || status === 403) return true;
        if (!data || typeof data !== 'object') return false;
        if (String(data.errorCode || '') === '200401') return true;
        const detail = String(data.detail || data.message || '');
        return /invalid token|expired token|token.*(invalid|expired)/i.test(detail);
    },

    isAuthenticationError(error) {
        return Boolean(error && error.isAuthenticationError);
    },

    /** 登录 */
    async login() {
        const data = await this._request('POST', '/rest-auth/login/', {
            username: this.username,
            password: this.password,
        });
        if (!data.key) {
            throw new Error('登录成功但响应中未找到 Token key');
        }
        this.token = data.key;
        return this.token;
    },

    /** 登出当前会话 */
    async logout() {
        return this._request('GET', '/rest-auth/logout/');
    },

    /** 获取单个项目 */
    async getProject(projectId) {
        return this._request('GET', `/api/v1/project/${encodeURIComponent(String(projectId))}`);
    },

    /** 获取项目分页 */
    async getProjectsPage(keyword = '', page = 1, pageSize = 20) {
        const params = new URLSearchParams({
            page: String(page),
            pageSize: String(pageSize),
            name: keyword,
        });
        const data = await this._request('GET', `/api/v1/project/?${params}`);
        const projects = this._asList(data);
        return {
            projects,
            page: Number(data?.page) || page,
            pageSize: Number(data?.pageSize) || pageSize,
            count: Number(data?.count) || projects.length,
        };
    },
    /** 获取版本列表 */
    async getVersions(projectId) {
        const params = new URLSearchParams({ project_id: String(projectId) });
        const data = await this._request('GET', `/api/v1/version/?${params}`);
        return this._asList(data);
    },

    /** 获取模块/组件列表 */
    async getModules(versionId) {
        const params = new URLSearchParams({ version_id: String(versionId), git_tag: 'True' });
        const data = await this._request('GET', `/api/v1/module/?${params}`);
        return this._asList(data);
    },

    /** 删除模块/组件 */
    async deleteModule(moduleId) {
        const data = await this._request(
            'DELETE',
            `/api/v1/module/${encodeURIComponent(String(moduleId))}`,
        );
        return data || { ok: true };
    },

    /** 修改模块端口映射 */
    async updateModulePort(modulePortId, payload) {
        return this._request(
            'PUT',
            `/api/v1/moduleport/${encodeURIComponent(String(modulePortId))}`,
            payload,
        );
    },

    /** 获取升级包记录 */
    _packageResource(family = 'upgrade') {
        return family === 'install' ? 'install' : 'update';
    },

    async getPackageRecords(family, versionId, offlineStatus = true) {
        const params = new URLSearchParams({
            version_id: String(versionId),
            offline_status: offlineStatus ? 'True' : 'False',
        });
        const resource = this._packageResource(family);
        const data = await this._request('GET', `/api/v1/recordsproject${resource}/?${params}`);
        return this._asList(data);
    },

    /** 删除升级包记录 */
    async deletePackageRecord(family, recordId) {
        const resource = this._packageResource(family);
        const data = await this._request('DELETE', `/api/v1/recordsproject${resource}/${recordId}`, {});
        return data || { ok: true };
    },

    /** 提交打包 */
    async submitPackage(family, versionId, payload) {
        const endpoint = family === 'install' ? 'install' : 'upgrade';
        const data = await this._request('POST', `/api/v1/packplus/${endpoint}/${versionId}`, payload);
        return data;
    },

    async getUpdateRecords(versionId, offlineStatus = true) {
        return this.getPackageRecords('upgrade', versionId, offlineStatus);
    },

    async deleteUpdateRecord(recordId) {
        return this.deletePackageRecord('upgrade', recordId);
    },

    async submitPack(versionId, payload) {
        return this.submitPackage('upgrade', versionId, payload);
    },

    /** 获取 Git refs（分支和标签） */
    async getRefs(gitUrl) {
        const data = await this._request('POST', '/api/v1/refs/', { git_url: gitUrl });
        return data;
    },

    /** 获取 Git 配置 */
    async getGitConfig(gitUrl, branch) {
        const data = await this._request('POST', '/api/v1/git_config/', {
            git_url: gitUrl,
            branch: branch,
        });
        return data;
    },

    /** 更新模块 */
    async updateModule(moduleId, payload) {
        const data = await this._request('PUT', `/api/v1/module/${moduleId}`, payload);
        return data;
    },

    /** 上传到 Seafile 网盘 */
    async uploadToSeafile(storagePath) {
        const data = await this._request('POST', '/api/v1/package/2seafile', {
            storagePath: storagePath,
        });
        return data;
    },

    /** 查询上传进度 */
    async getUploadProgress(taskId) {
        const params = new URLSearchParams({ task_id: taskId });
        const data = await this._request('GET', `/api/v1/package/progress/${taskId}?${params}`);
        return data;
    },

    /** 解析 API 响应为列表 */
    _asList(data) {
        if (Array.isArray(data)) {
            return data.filter(item => item && typeof item === 'object');
        }
        if (data && typeof data === 'object') {
            for (const key of ['results', 'data', 'list', 'items']) {
                if (Array.isArray(data[key])) {
                    return data[key].filter(item => item && typeof item === 'object');
                }
            }
        }
        return [];
    },
};
