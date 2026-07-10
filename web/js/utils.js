/**
 * ifaas-packing 工具函数（对应原 api.py 中的 pick / object_id / module_id 等）
 */

/** 从对象中取第一个非空值 */
function pick(data, ...keys) {
    for (const key of keys) {
        const value = data[key];
        if (value !== null && value !== undefined && value !== '') {
            return String(value);
        }
    }
    return '';
}

/** 从数据中提取对象 ID */
function objectId(data) {
    return pick(data, 'id', 'pk', 'project_id', 'version_id');
}

/** 从模块数据中提取模块 ID */
function moduleId(data) {
    return pick(data, 'pk', 'id');
}

/** 从模块数据中提取 git URL */
function moduleGitUrl(data) {
    const gitUrl = data['git_url'];
    if (gitUrl && typeof gitUrl === 'object') {
        return pick(gitUrl, 'git_url', 'url');
    }
    if (gitUrl) return String(gitUrl);
    return pick(data, 'git', 'repository', 'repo_url');
}

/**
 * Toast 消息提示
 * 在页面右上角显示自动消失的提示
 */
function showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    // 触发动画
    requestAnimationFrame(() => toast.classList.add('toast-visible'));

    setTimeout(() => {
        toast.classList.remove('toast-visible');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function showInfo(title, content) {
    showToast(`${title}：${content}`, 'info');
}

function showSuccess(title, content) {
    showToast(`${title}：${content}`, 'success');
}

function showError(title, content) {
    showToast(`${title}：${content}`, 'error');
}

/**
 * 格式化 Unix 毫秒时间戳为可读字符串
 */
function formatTime(ms) {
    if (!ms) return '-';
    try {
        const date = new Date(Number(ms));
        if (isNaN(date.getTime())) return String(ms);
        return date.toLocaleString('zh-CN');
    } catch {
        return String(ms);
    }
}

/**
 * 防抖
 */
function debounce(fn, delay = 300) {
    let timer = null;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

/**
 * HTML 转义
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 复制文本到剪贴板
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showSuccess('复制成功', '已复制到剪贴板');
    } catch {
        // fallback
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showSuccess('复制成功', '已复制到剪贴板');
    }
}
