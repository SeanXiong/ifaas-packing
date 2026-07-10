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

    async loadFavorites() {
        try {
            const data = await this._read('favorites');
            if (!data || !Array.isArray(data.project_ids)) return new Set();
            return new Set(data.project_ids.map(String));
        } catch {
            return new Set();
        }
    },

    async saveFavorites(favorites) {
        const data = { project_ids: [...favorites].sort() };
        await this._write('favorites', data);
    },

    async toggleFavorite(projectId) {
        const favs = await this.loadFavorites();
        const key = String(projectId);
        if (favs.has(key)) {
            favs.delete(key);
            await this.saveFavorites(favs);
            return false; // 已取消收藏
        } else {
            favs.add(key);
            await this.saveFavorites(favs);
            return true; // 已收藏
        }
    },

    /* ---- 登录凭据 ---- */

    async loadCredentials() {
        try {
            const data = await this._read('credentials');
            if (!data) return this.defaults();
            return {
                username: String(data.username || 'sujiangang'),
                password: String(data.password || 'Intellif@123'),
                remember: Boolean(data.remember ?? true),
            };
        } catch {
            return this.defaults();
        }
    },

    defaults() {
        return {
            username: 'sujiangang',
            password: 'Intellif@123',
            remember: true,
        };
    },

    async saveCredentials(username, password, remember) {
        const data = {
            username: remember ? username : '',
            password: remember ? password : '',
            remember: remember,
        };
        await this._write('credentials', data);
    },
};
