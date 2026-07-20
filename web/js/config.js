/**
 * ifaas-packing 配置读写（对应原 storage.py）
 * 通过 server.py 的 /api/config/ 端点读写 JSON 配置文件
 */

const ConfigStore = {
    async _read(name) {
        const resp = await fetch(`/api/config/${name}`);
        if (!resp.ok) {
            if (resp.status === 404) return null;
            throw new Error(`读取配置 ${name} 失败：HTTP ${resp.status}`);
        }
        return resp.json();
    },

    async _write(name, data) {
        const resp = await fetch(`/api/config/${name}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!resp.ok) {
            throw new Error(`写入配置 ${name} 失败：HTTP ${resp.status}`);
        }
        return resp.json();
    },

    /* ---- 收藏 ---- */

    async loadLoginProfile(username) {
        const account = String(username || '').trim();
        if (!/^[a-zA-Z0-9_-]+$/.test(account)) return null;
        try {
            const data = await this._read('login-profiles');
            const profile = data && data.accounts && data.accounts[account];
            if (!profile || typeof profile !== 'object') return null;
            const profileUsername = String(profile.username || account).trim();
            const password = String(profile.password || '');
            return profileUsername && password ? { username: profileUsername, password } : null;
        } catch {
            return null;
        }
    },

    async saveLoginProfile(username, password) {
        const account = String(username || '').trim();
        const secret = String(password || '');
        if (!/^[a-zA-Z0-9_-]+$/.test(account) || !secret) {
            throw new Error('登录账号或密码格式无效。');
        }
        const data = await this._read('login-profiles');
        const accounts = data && data.accounts && typeof data.accounts === 'object'
            ? data.accounts
            : {};
        accounts[account] = { username: account, password: secret };
        await this._write('login-profiles', { accounts });
    },

    _favoriteAccount(username) {
        const account = String(username || '').trim();
        if (!account) throw new Error('未找到当前登录账号。');
        return account;
    },

    async _favoriteData(username) {
        const account = this._favoriteAccount(username);
        const data = await this._read('favorites');
        const accounts = data && data.accounts && typeof data.accounts === 'object'
            ? data.accounts
            : {};

        // 兼容历史的单账号收藏文件：首次登录时归属到当前账号。
        if (data && Array.isArray(data.project_ids)) {
            accounts[account] = { project_ids: data.project_ids.map(String) };
            await this._write('favorites', { accounts });
        }
        return { account, accounts };
    },

    async loadFavorites(username) {
        try {
            const { account, accounts } = await this._favoriteData(username);
            const entry = accounts[account] || {};
            const projectIds = Array.isArray(entry.projects)
                ? entry.projects.map(project => project && (project.id ?? project.pk)).filter(Boolean)
                : entry.project_ids;
            return new Set(Array.isArray(projectIds) ? projectIds.map(String) : []);
        } catch {
            return new Set();
        }
    },

    async loadFavoriteProjects(username) {
        const { account, accounts } = await this._favoriteData(username);
        const projects = accounts[account] && accounts[account].projects;
        return Array.isArray(projects) ? projects.filter(project => project && typeof project === 'object') : null;
    },

    async saveFavoriteProjects(username, projects) {
        const { account, accounts } = await this._favoriteData(username);
        accounts[account] = {
            projects: (Array.isArray(projects) ? projects : [])
                .filter(project => project && typeof project === 'object'),
        };
        await this._write('favorites', { accounts });
    },

    async saveFavorites(username, favorites) {
        const { account, accounts } = await this._favoriteData(username);
        accounts[account] = { project_ids: [...favorites].map(String).sort() };
        await this._write('favorites', { accounts });
    },

    async toggleFavorite(username, projectId) {
        const favs = await this.loadFavorites(username);
        const key = String(projectId);
        if (favs.has(key)) {
            favs.delete(key);
            await this.saveFavorites(username, favs);
            return false; // 已取消收藏
        } else {
            favs.add(key);
            await this.saveFavorites(username, favs);
            return true; // 已收藏
        }
    },

};
