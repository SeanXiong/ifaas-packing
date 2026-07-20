/**
 * ifaas-packing 主应用逻辑（对应原 main_window.py 的 PackingInterface 等）
 */

/* ================================================================
 * 全局状态
 * ================================================================ */

const state = {
    page: 'login',            // 'login' | 'main'
    currentUsername: '',
    projects: [],
    favoriteProjects: [],
    favoritePage: { page: 1, pageSize: 20 },
    allProjectsLoaded: false,
    projectPage: { page: 1, pageSize: 20, count: 0 },
    currentProject: null,
    currentVersion: null,
    moduleRows: [],           // 原始模块数据
    projectTab: 'favorite',   // 'favorite' | 'all'
    favorites: new Set(),
    uploadTasks: {},          // taskId -> PackageRecord 映射
    uploadTimer: null,        // 上传进度轮询定时器
    currentRecordType: { family: 'install', offline: true },
};

const SESSION_TOKEN_KEY = 'ifaas-packing.token';
const SESSION_USERNAME_KEY = 'ifaas-packing.username';

const PACKAGE_TYPE_DEFINITIONS = {
    upgrade: {
        label: '升级包',
        recordsPath: '/api/v1/recordsprojectupdate/',
    },
    install: {
        label: '安装包',
        recordsPath: '/api/v1/recordsprojectinstall/',
    },
};

function getPackageType(family = 'upgrade', offline = true) {
    const definition = PACKAGE_TYPE_DEFINITIONS[family] || PACKAGE_TYPE_DEFINITIONS.upgrade;
    return {
        family: family === 'install' ? 'install' : 'upgrade',
        offline: Boolean(offline),
        label: `${offline ? '离线' : '在线'}${definition.label}`,
        recordsPath: definition.recordsPath,
    };
}

function isSeafileUploadAllowed(packageType) {
    return Boolean(packageType?.offline);
}

function getPackageTypeOptions() {
    return [
        getPackageType('upgrade', true),
        getPackageType('install', true),
        getPackageType('upgrade', false),
        getPackageType('install', false),
    ];
}

function getPackageFamilies() {
    return [
        { value: 'upgrade', label: '升级包' },
        { value: 'install', label: '安装包' },
    ];
}

function getNetworkTypes() {
    return [
        { value: 'offline', label: '离线' },
        { value: 'online', label: '在线' },
    ];
}

function getDefaultPackParameters() {
    return {
        family: 'install',
        offline: true,
        support_cpu: 'x86_64',
        namespace: 'basic-app',
        seafile: false,
    };
}

function selectPackageRecordType(packageType) {
    state.currentRecordType = packageType;
    return state.currentRecordType;
}

function getLoginProfileName(search) {
    const profile = new URLSearchParams(search || '').get('profile') || '';
    return /^[a-zA-Z0-9_-]+$/.test(profile) ? profile : '';
}

async function prefillLoginProfile() {
    const profileName = getLoginProfileName(window.location.search);
    if (!profileName) return false;
    const profile = await ConfigStore.loadLoginProfile(profileName);
    if (!profile) return false;
    document.getElementById('loginUsername').value = profile.username;
    document.getElementById('loginPassword').value = profile.password;
    return true;
}

/* ================================================================
 * 登录页
 * ================================================================ */

function showLoginPage() {
    state.page = 'login';
    document.getElementById('loginPage').style.display = 'flex';
    document.getElementById('mainPage').style.display = 'none';
    document.getElementById('loginUsername').value = '';
    document.getElementById('loginPassword').value = '';
}

function hideLoginPage() {
    document.getElementById('loginPage').style.display = 'none';
    document.getElementById('mainPage').style.display = 'flex';
    state.page = 'main';
    requestAnimationFrame(measureSplitterColumns);
}

function saveSessionToken(token, username) {
    sessionStorage.setItem(SESSION_TOKEN_KEY, token);
    sessionStorage.setItem(SESSION_USERNAME_KEY, username);
    state.currentUsername = username;
    updateUserMenu();
}

function clearSessionToken() {
    sessionStorage.removeItem(SESSION_TOKEN_KEY);
    sessionStorage.removeItem(SESSION_USERNAME_KEY);
    ApiClient.token = null;
    state.currentUsername = '';
    updateUserMenu();
}

function updateUserMenu() {
    const nameElement = document.getElementById('userMenuName');
    if (nameElement) nameElement.textContent = state.currentUsername || '当前用户';
}

function setUserMenuOpen(open) {
    const menu = document.getElementById('userMenu');
    const trigger = document.getElementById('userMenuTrigger');
    menu.classList.toggle('open', open);
    trigger.setAttribute('aria-expanded', String(open));
}

function showUserProfile() {
    const overlay = document.getElementById('modalOverlay');
    const body = document.getElementById('modalBody');
    body.className = 'modal-body user-profile-modal';
    body.innerHTML = `
        <h3>个人信息</h3>
        <div class="user-profile-row"><span>账号</span><strong>${escapeHtml(state.currentUsername || '-')}</strong></div>
        <div class="modal-actions"><button type="button" class="btn btn-secondary" id="userProfileClose">关闭</button></div>
    `;
    overlay.style.display = 'flex';
    document.getElementById('userProfileClose').onclick = closeModal;
}

async function logout() {
    const button = document.getElementById('logoutButton');
    button.disabled = true;
    button.textContent = '退出中...';
    try {
        await ApiClient.logout();
        clearSessionToken();
        setUserMenuOpen(false);
        showLoginPage();
        showInfo('已退出登录', '当前会话已安全退出。');
    } catch (error) {
        showRequestError('退出登录失败', error);
    } finally {
        button.disabled = false;
        button.textContent = '退出登录';
    }
}

async function restoreSession() {
    const token = sessionStorage.getItem(SESSION_TOKEN_KEY);
    if (!token) {
        await showLoginPage();
        await prefillLoginProfile();
        return false;
    }
    const username = sessionStorage.getItem(SESSION_USERNAME_KEY);
    if (!username) {
        clearSessionToken();
        await showLoginPage();
        await prefillLoginProfile();
        return false;
    }
    ApiClient.token = token;
    ApiClient.username = username;
    state.currentUsername = username;
    updateUserMenu();
    hideLoginPage();
    await loadFavoriteProjects();
    return true;
}

function handleSessionExpired() {
    if (state.page === 'login') return;
    clearSessionToken();
    showLoginPage();
    showError('登录已失效', '当前会话已过期，请重新登录。');
}

function showRequestError(title, error) {
    if (!ApiClient.isAuthenticationError(error)) {
        showError(title, error.message);
    }
}

async function doLogin() {
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    if (!username || !password) {
        showError('登录失败', '请输入账号和密码。');
        return;
    }

    const btn = document.getElementById('loginButton');
    btn.disabled = true;
    btn.textContent = '登录中...';

    try {
        ApiClient.init(username, password);
        await ApiClient.login();
        saveSessionToken(ApiClient.token, username);
        ConfigStore.saveLoginProfile(username, password).catch(() => {
            showError('账号信息保存失败', '本次登录不受影响，但下次无法自动预填账号密码。');
        });
        hideLoginPage();
        await loadFavoriteProjects();
        showInfo('登录成功', '正在加载项目...');
    } catch (err) {
        showRequestError('登录失败', err);
    } finally {
        btn.disabled = false;
        btn.textContent = '登录';
    }
}

/* ================================================================
 * 项目列表（左栏）
 * ================================================================ */

async function loadFavoriteProjects() {
    try {
        state.favorites = await ConfigStore.loadFavorites(state.currentUsername);
        const projects = await Promise.all(
            [...state.favorites].map(projectId => ApiClient.getProject(projectId)),
        );
        state.favoriteProjects = projects.filter(project => project && typeof project === 'object');
        state.favoritePage.page = 1;
        renderProjects();
        document.getElementById('projectPagination').classList.toggle('hidden', state.projectTab !== 'favorite');
        renderProjectPagination();
    } catch (err) {
        showRequestError('收藏项目查询失败', err);
    }
}

async function loadProjectPage(page = 1) {
    const keyword = document.getElementById('projectSearch').value.trim();
    try {
        const result = await ApiClient.getProjectsPage(keyword, page);
        state.projects = result.projects;
        state.projectPage = result;
        state.allProjectsLoaded = true;
        renderProjects();
        renderProjectPagination();
        if (keyword) {
            showInfo('项目已加载', `共 ${result.count} 个项目`);
        }
    } catch (err) {
        showRequestError('项目查询失败', err);
    }
}

const debouncedSearch = debounce(() => loadProjectPage(1), 300);

function renderProjects() {
    const favList = document.getElementById('favoriteList');
    const allList = document.getElementById('allProjectList');

    favList.innerHTML = '';
    allList.innerHTML = '';

    const sortProjects = projects => [...projects].sort((a, b) => {
        const nameA = pick(a, 'name', 'project_name');
        const nameB = pick(b, 'name', 'project_name');
        return nameA.localeCompare(nameB, 'zh');
    });

    const favoriteProjects = paginateProjects(
        sortProjects(state.favoriteProjects),
        state.favoritePage.page,
        state.favoritePage.pageSize,
    );
    for (const project of favoriteProjects) {
        favList.appendChild(createProjectRow(project, true));
    }
    for (const project of sortProjects(state.projects)) {
        allList.appendChild(createProjectRow(project, state.favorites.has(objectId(project))));
    }
}

function paginateProjects(projects, page, pageSize) {
    const start = (page - 1) * pageSize;
    return projects.slice(start, start + pageSize);
}

function currentProjectPagination() {
    if (state.projectTab === 'favorite') {
        return {
            page: state.favoritePage.page,
            pageSize: state.favoritePage.pageSize,
            count: state.favoriteProjects.length,
        };
    }
    return state.projectPage;
}

function renderProjectPagination() {
    const { page, pageSize, count } = currentProjectPagination();
    const totalPages = Math.max(1, Math.ceil(count / pageSize));
    document.getElementById('projectPageInfo').textContent = `第 ${page} / ${totalPages} 页，共 ${count} 个项目`;
    document.getElementById('projectPrevPage').disabled = page <= 1;
    document.getElementById('projectNextPage').disabled = page >= totalPages;
}

async function goProjectPage(page) {
    const totalPages = Math.max(1, Math.ceil(state.projectPage.count / state.projectPage.pageSize));
    if (page < 1 || page > totalPages || page === state.projectPage.page) return;
    await loadProjectPage(page);
}

function goFavoritePage(page) {
    const totalPages = Math.max(1, Math.ceil(state.favoriteProjects.length / state.favoritePage.pageSize));
    if (page < 1 || page > totalPages || page === state.favoritePage.page) return;
    state.favoritePage.page = page;
    renderProjects();
    renderProjectPagination();
}

function goCurrentProjectPage(offset) {
    if (state.projectTab === 'favorite') {
        goFavoritePage(state.favoritePage.page + offset);
    } else {
        goProjectPage(state.projectPage.page + offset);
    }
}
function createProjectRow(project, favorited) {
    const div = document.createElement('div');
    div.className = 'list-row project-row';
    const pid = objectId(project);
    if (pid) {
        div.dataset.projectId = pid;
        div.classList.toggle('selected', objectId(state.currentProject || {}) === pid);
    }
    div.innerHTML = `
        <span class="row-name">${escapeHtml(pick(project, 'name', 'project_name', 'title', '未命名项目'))}</span>
        <button class="fav-btn" title="收藏 / 取消收藏">${favorited ? '★' : '☆'}</button>
    `;

    div.onclick = () => selectProject(project);
    div.querySelector('.fav-btn').onclick = (e) => {
        e.stopPropagation();
        toggleFavorite(project);
    };

    return div;
}

async function toggleFavorite(project) {
    const pid = objectId(project);
    if (!pid) {
        showError('收藏失败', '当前项目缺少 id/pk 字段。');
        return;
    }
    const favorited = await ConfigStore.toggleFavorite(state.currentUsername, pid);
    state.favorites = await ConfigStore.loadFavorites(state.currentUsername);
    if (favorited && !state.favoriteProjects.some(item => objectId(item) === pid)) {
        state.favoriteProjects.push(project);
    }
    if (!favorited) {
        state.favoriteProjects = state.favoriteProjects.filter(item => objectId(item) !== pid);
    }
    const favoritePageCount = Math.max(1, Math.ceil(state.favoriteProjects.length / state.favoritePage.pageSize));
    state.favoritePage.page = Math.min(state.favoritePage.page, favoritePageCount);
    renderProjects();
    renderProjectPagination();
    showSuccess('收藏状态已更新', `${favorited ? '已收藏' : '已取消收藏'}：${pick(project, 'name', 'project_name', pid)}`);
}

async function switchProjectTab(tab) {
    state.projectTab = tab;
    document.getElementById('pivotFav').classList.toggle('active', tab === 'favorite');
    document.getElementById('pivotAll').classList.toggle('active', tab === 'all');
    document.getElementById('favoriteList').classList.toggle('hidden', tab !== 'favorite');
    document.getElementById('allProjectList').classList.toggle('hidden', tab !== 'all');
    document.getElementById('projectPagination').classList.remove('hidden');
    if (tab === 'all' && !state.allProjectsLoaded) {
        await loadProjectPage(1);
    }
    renderProjectPagination();
}

function updateProjectSelection() {
    const selectedId = objectId(state.currentProject || {});
    document.querySelectorAll('.project-row').forEach(row => {
        row.classList.toggle('selected', Boolean(selectedId) && row.dataset.projectId === selectedId);
    });
}

/* ================================================================
 * 版本列表（中栏）
 * ================================================================ */

async function selectProject(project) {
    state.currentProject = project;
    state.currentVersion = null;
    updateProjectSelection();
    document.getElementById('versionList').innerHTML = '';
    clearModules();

    const projectId = objectId(project);
    if (!projectId) {
        showError('版本查询失败', '当前项目缺少 id/pk 字段。');
        return;
    }

    const name = pick(project, 'name', 'project_name', '当前项目');
    document.getElementById('versionHint').textContent = `当前项目：${name}`;

    try {
        const versions = await ApiClient.getVersions(projectId);
        renderVersions(versions);
        showInfo('版本已加载', `共 ${versions.length} 个版本`);
    } catch (err) {
        showRequestError('版本查询失败', err);
    }
}

function renderVersions(versions) {
    const list = document.getElementById('versionList');
    list.innerHTML = '';
    for (const version of versions) {
        const row = createVersionRow(version);
        list.appendChild(row);
    }
}

function createVersionRow(version) {
    const div = document.createElement('div');
    div.className = 'list-row version-row';
    const vid = objectId(version);
    if (vid) {
        div.dataset.versionId = vid;
        div.classList.toggle('selected', objectId(state.currentVersion || {}) === vid);
    }
    const name = pick(version, 'update_version', '未命名版本');
    div.innerHTML = `
        <span class="row-name">${escapeHtml(name)}</span>
        <button class="btn btn-sm version-records-btn">打包记录</button>
    `;
    div.querySelector('.version-records-btn').onclick = (e) => {
        e.stopPropagation();
        viewVersionRecords(version, e.currentTarget);
    };
    div.onclick = () => selectVersion(version);
    return div;
}

function updateVersionSelection() {
    const selectedId = objectId(state.currentVersion || {});
    document.querySelectorAll('.version-row').forEach(row => {
        row.classList.toggle('selected', Boolean(selectedId) && row.dataset.versionId === selectedId);
    });
}

async function viewVersionRecords(version, triggerButton) {
    state.currentVersion = version;
    updateVersionSelection();
    const versionName = pick(version, 'update_version', '当前版本');
    document.getElementById('packageHint').textContent = `当前版本：${versionName}`;
    await loadPackageRecords(triggerButton);
}

/* ================================================================
 * 模块/组件列表（右栏）
 * ================================================================ */

async function selectVersion(version) {
    state.currentVersion = version;
    updateVersionSelection();
    clearModules();

    const versionName = pick(version, 'update_version', '当前版本');
    document.getElementById('packageHint').textContent = `当前版本：${versionName}`;

    const versionId = objectId(version);
    if (!versionId) {
        showError('组件查询失败', '当前版本缺少 id/pk 字段。');
        return;
    }

    setModuleLoading(true);
    setRightPanelLoading(true, '组件加载中...');
    try {
        const modules = await ApiClient.getModules(versionId);
        state.moduleRows = modules;
        renderModules(modules);
        document.getElementById('packButton').disabled = !modules.length;
        showInfo('服务已加载', `共 ${modules.length} 个服务组件`);
    } catch (err) {
        showRequestError('组件查询失败', err);
    } finally {
        setModuleLoading(false);
        setRightPanelLoading(false);
    }
}

function renderModules(modules) {
    const list = document.getElementById('moduleList');
    list.innerHTML = `
        <div class="module-table-header">
            <span>服务名</span>
            <span>服务版本</span>
            <span>操作</span>
        </div>
    `;
    modules.forEach((mod, index) => {
        const row = createModuleRow(mod, index);
        list.appendChild(row);
    });
}

function createModuleRow(mod, index) {
    const div = document.createElement('div');
    div.className = 'module-row';
    div.dataset.index = String(index);
    const name = pick(mod, 'name', 'module_name', '未命名服务');
    const branch = pick(mod, 'branch', 'ref_name', 'git_branch', 'tag', '-');
    div.innerHTML = `
        <label class="module-name-cell">
            <input type="checkbox" class="module-checkbox">
            <span class="row-name">${escapeHtml(name)}</span>
        </label>
        <span class="module-version-cell branch-text">${escapeHtml(branch)}</span>
        <button class="btn btn-sm edit-branch-btn">切换分支</button>
    `;

    const checkbox = div.querySelector('.module-checkbox');
    checkbox.onchange = () => syncSelectAllState();

    div.querySelector('.edit-branch-btn').onclick = (e) => {
        e.stopPropagation();
        changeModuleBranch(mod, div);
    };

    return div;
}

function clearModules() {
    state.moduleRows = [];
    document.getElementById('moduleList').innerHTML = '';
    document.getElementById('selectAllCheckbox').checked = false;
    document.getElementById('packButton').disabled = true;
}

function setRightPanelLoading(loading, message = '组件加载中...') {
    const overlay = document.getElementById('rightPanelLoading');
    overlay.classList.toggle('hidden', !loading);
    if (loading) {
        document.getElementById('rightPanelLoadingText').textContent = message;
    }
}

function setModuleLoading(loading) {
    document.getElementById('moduleLoading').classList.toggle('hidden', !loading);
    document.getElementById('selectAllCheckbox').disabled = loading;
    document.getElementById('moduleSearch').disabled = loading;
    const btn = document.getElementById('packButton');
    if (loading) {
        btn.textContent = '加载中...';
        btn.disabled = true;
    } else {
        btn.textContent = '开始打包';
        btn.disabled = !(state.currentVersion && state.moduleRows.length);
    }
}

function filterModules() {
    const keyword = document.getElementById('moduleSearch').value.trim().toLowerCase();
    const rows = document.querySelectorAll('#moduleList .module-row');
    rows.forEach(row => {
        const mod = state.moduleRows[Number(row.dataset.index)];
        if (!mod) return;
        const text = (pick(mod, 'name', 'module_name') + ' ' + pick(mod, 'branch', 'ref_name', 'git_branch', 'tag')).toLowerCase();
        row.style.display = keyword === '' || text.includes(keyword) ? '' : 'none';
    });
    syncSelectAllState();
}

function selectAllModules(checked) {
    const rows = document.querySelectorAll('#moduleList .module-row');
    rows.forEach(row => {
        if (row.style.display !== 'none') {
            const cb = row.querySelector('.module-checkbox');
            if (cb) cb.checked = checked;
        }
    });
}

function syncSelectAllState() {
    const rows = [...document.querySelectorAll('#moduleList .module-row')]
        .filter(r => r.style.display !== 'none');
    if (!rows.length) return;
    const allChecked = rows.every(r => r.querySelector('.module-checkbox')?.checked);
    const cb = document.getElementById('selectAllCheckbox');
    cb.checked = allChecked;
    cb.indeterminate = !allChecked && rows.some(r => r.querySelector('.module-checkbox')?.checked);
}

/* ================================================================
 * 修改分支弹窗
 * ================================================================ */

async function changeModuleBranch(mod, rowElement) {
    const gitUrl = moduleGitUrl(mod);
    if (!gitUrl) {
        showError('无法修改分支', '当前服务缺少 git_url 字段。');
        return;
    }

    const btn = rowElement.querySelector('.edit-branch-btn');
    btn.disabled = true;

    try {
        const refs = await ApiClient.getRefs(gitUrl);
        btn.disabled = false;
        showBranchDialog(mod, rowElement, gitUrl, refs);
    } catch (err) {
        btn.disabled = false;
        showRequestError('获取分支失败', err);
    }
}

function showBranchDialog(mod, rowElement, gitUrl, refs) {
    const data = refs.data || refs || {};
    const branches = data.branches || [];
    const tags = data.tags || [];
    const allRefs = [...branches, ...tags];
    const serviceName = pick(mod, 'name', 'module_name', '当前服务');
    const currentBranch = pick(mod, 'branch', 'ref_name', 'git_branch', 'tag');

    const overlay = document.getElementById('modalOverlay');
    const body = document.getElementById('modalBody');

    body.innerHTML = `
        <h3>修改分支</h3>
        <p class="muted">${escapeHtml(serviceName)}</p>
        <div class="form-group">
            <label>选择或输入目标分支</label>
            <div class="branch-select">
                <input type="text" id="branchInput" class="form-input"
                       value="${escapeHtml(currentBranch)}"
                       placeholder="输入或选择分支/标签">
                <div id="branchOptions" class="branch-options">
                    ${allRefs.map(b => `<button type="button" class="branch-option" data-value="${escapeHtml(b)}">${escapeHtml(b)}</button>`).join('')}
                </div>
            </div>
        </div>
        <div class="modal-actions">
            <button class="btn btn-secondary" id="branchCancel">取消</button>
            <button class="btn btn-primary" id="branchConfirm">确认修改</button>
        </div>
    `;

    overlay.style.display = 'flex';
    const branchInput = document.getElementById('branchInput');
    const branchOptions = document.getElementById('branchOptions');

    const syncBranchOptions = () => {
        const keyword = branchInput.value.trim().toLowerCase();
        branchOptions.querySelectorAll('.branch-option').forEach(option => {
            option.hidden = keyword !== '' && !option.dataset.value.toLowerCase().includes(keyword);
        });
    };

    branchInput.onfocus = () => branchOptions.classList.add('open');
    branchInput.oninput = syncBranchOptions;
    branchOptions.querySelectorAll('.branch-option').forEach(option => {
        option.onclick = () => {
            branchInput.value = option.dataset.value;
            branchOptions.classList.remove('open');
        };
    });
    const cancelButton = document.getElementById('branchCancel');
    const confirmButton = document.getElementById('branchConfirm');
    cancelButton.onclick = closeModal;
    confirmButton.onclick = async () => {
        const branch = branchInput.value.trim();
        if (!branch) {
            showError('无法修改分支', '目标分支不能为空。');
            return;
        }
        setBranchSaveLoading(confirmButton, cancelButton, true);
        try {
            await updateModuleBranch(mod, rowElement, gitUrl, branch);
            closeModal();
        } catch (err) {
            showRequestError('修改分支失败', err);
            setBranchSaveLoading(confirmButton, cancelButton, false);
        }
    };
}

function setBranchSaveLoading(confirmButton, cancelButton, loading) {
    confirmButton.disabled = loading;
    cancelButton.disabled = loading;
    confirmButton.textContent = loading ? '正在保存...' : '确认修改';
}

async function updateModuleBranch(mod, rowElement, gitUrl, branch) {
    const serviceName = pick(mod, 'name', 'module_name');
    const gitId = mod.git_url && typeof mod.git_url === 'object'
        ? (mod.git_url.id ?? mod.git_url.pk ?? mod.git_url.git_url)
        : mod.git_url;
    if (!gitId) throw new Error('当前服务缺少 git_url 字段。');

    const payload = {
        name: serviceName,
        custom_name: pick(mod, 'custom_name') || serviceName,
        service_type: mod.service_type ?? 1,
        branch: branch,
        APP_ID: mod.APP_ID || serviceName,
        git_config_path: pick(mod, 'git_config_path') || 'build_ci/config.yml',
        is_image: mod.is_image ?? true,
        version: objectId(state.currentVersion || {}),
        git_url: gitId,
    };
    const mid = moduleId(mod);
    if (!mid) throw new Error('当前服务缺少 pk/id 字段。');

    const result = await ApiClient.updateModule(mid, payload);
    const resultCode = result.resultCode;
    if (resultCode !== null && resultCode !== undefined && resultCode !== 0) {
        throw new Error(result.message || '修改服务分支失败。');
    }

    // 更新本地状态和 UI
    // 以后端保存后返回的组件数据为准，供后续打包和列表展示使用。
    const updatedModule = result && typeof result.data === 'object' ? result.data : result;
    if (updatedModule && typeof updatedModule === 'object') {
        Object.assign(mod, updatedModule);
    }
    const displayedBranch = pick(updatedModule, 'branch') || branch;
    mod.branch = displayedBranch;
    rowElement.querySelector('.branch-text').textContent = displayedBranch;
    showSuccess('修改成功', `${serviceName} 分支已更新为：${displayedBranch}`);}

/* ================================================================
 * 升级包记录弹窗
 * ================================================================ */

async function loadPackageRecords(triggerButton, packageType = state.currentRecordType) {
    if (!state.currentVersion) {
        showError('升级包查询失败', '请先选择一个版本。');
        return;
    }
    const versionId = objectId(state.currentVersion);
    if (!versionId) {
        showError('升级包查询失败', '当前版本缺少 id/pk 字段。');
        return;
    }

    const btn = triggerButton || null;
    const originalText = btn ? btn.textContent : '';
    if (btn) {
        btn.disabled = true;
        btn.textContent = '查询中...';
    }

    try {
        const records = await ApiClient.getPackageRecords(packageType.family, versionId, packageType.offline);
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
        showRecordsDialog(records, packageType);
    } catch (err) {
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
        }
        showRequestError('升级包查询失败', err);
    }
}

function showRecordsDialog(records, packageType = state.currentRecordType) {
    const versionName = pick(state.currentVersion || {}, 'update_version', '当前版本');
    const overlay = document.getElementById('modalOverlay');
    const body = document.getElementById('modalBody');
    body.className = 'modal-body modal-wide';
    const recordModels = records.map((record, index) => normalizeUpdateRecord(record, index));

    body.innerHTML = `
        <div class="records-header">
            <div>
                <h3>打包记录</h3>
                <p class="muted">${escapeHtml(versionName)} · 共 ${records.length} 条记录</p>
            </div>
            <button class="btn btn-secondary" id="recordsCloseTop">关闭</button>
        </div>
        <div class="records-toolbar records-type-toolbar">
            <label for="recordPackageFamily">包类型</label>
            <select id="recordPackageFamily" class="form-select">
                ${getPackageFamilies().map(option => `<option value="${option.value}" ${option.value === packageType.family ? 'selected' : ''}>${option.label}</option>`).join('')}
            </select>
            <label for="recordNetworkType">网络类型</label>
            <select id="recordNetworkType" class="form-select">
                ${getNetworkTypes().map(option => `<option value="${option.value}" ${(option.value === 'offline') === packageType.offline ? 'selected' : ''}>${option.label}</option>`).join('')}
            </select>
        </div>
        <div class="records-list artifact-list" id="recordsList"></div>
        <div class="module-drawer hidden" id="moduleDrawer">
            <div class="module-drawer-mask"></div>
            <aside class="module-drawer-panel">
                <div class="module-drawer-head">
                    <div>
                        <p class="drawer-kicker">模块详情</p>
                        <h3 id="moduleDrawerTitle">模块详情</h3>
                    </div>
                    <button class="drawer-close" type="button" id="moduleDrawerClose">×</button>
                </div>
                <div id="moduleDrawerContent"></div>
            </aside>
        </div>
    `;

    overlay.style.display = 'flex';
    document.getElementById('recordsCloseTop').onclick = closeModal;
    document.getElementById('moduleDrawerClose').onclick = closeModuleDrawer;
    body.querySelector('.module-drawer-mask').onclick = closeModuleDrawer;

    const renderList = () => {
        const list = document.getElementById('recordsList');

        if (!recordModels.length) {
            list.innerHTML = `
                <div class="records-empty">
                    <div class="records-empty-icon">📦</div>
                    <strong>暂无升级包</strong>
                    <span>点击开始打包</span>
                </div>
            `;
            return;
        }

        list.innerHTML = recordModels.map(record => renderArtifactCard(record, packageType)).join('');
    };

    renderList();
    const changeRecordType = () => {
        state.currentRecordType = getPackageType(
            document.getElementById('recordPackageFamily').value,
            document.getElementById('recordNetworkType').value === 'offline',
        );
        loadPackageRecords(null, state.currentRecordType);
    };
    document.getElementById('recordPackageFamily').onchange = changeRecordType;
    document.getElementById('recordNetworkType').onchange = changeRecordType;

    body.onclick = async (event) => {
        const target = event.target;
        const card = target.closest?.('.record-card');
        const record = card ? recordModels[Number(card.dataset.index)] : null;

        if (target.closest?.('.copy-download-btn, .copy-intranet-btn')) {
            copyToClipboard(record?.downloadPath || '');
            return;
        }
        if (target.closest?.('.copy-extranet-btn')) {
            copyToClipboard(record?.seafilePath || '');
            return;
        }
        if (target.closest?.('.delete-record-btn')) {
            const deleted = await deletePackageRecord(card, target.closest('.delete-record-btn'), record?.raw, packageType);
            if (deleted) {
                await loadPackageRecords(null, packageType);
            }
            return;
        }
        if (target.closest?.('.upload-seafile-btn')) {
            const btn = target.closest('.upload-seafile-btn');
            if (!record?.storagePath) {
                showError('上传失败', '当前记录缺少 storage_path。');
                return;
            }
            await uploadToSeafile(card, btn, record.raw, record.storagePath);
            return;
        }
        const moduleCard = target.closest?.('.artifact-module-card');
        if (moduleCard) {
            const recordIndex = Number(moduleCard.dataset.recordIndex);
            const moduleIndex = Number(moduleCard.dataset.moduleIndex);
            openModuleDrawer(recordModels[recordIndex], recordModels[recordIndex].modules[moduleIndex]);
            return;
        }
        if (target.closest?.('.artifact-summary') && !target.closest?.('button, a')) {
            toggleArtifactDetail(card);
        }
    };
}

function parseRecordParams(record) {
    const raw = record?.params_detail?.params ?? record?.params;
    if (!raw) return {};
    if (typeof raw === 'object') return raw;
    if (typeof raw !== 'string') return {};

    const text = raw.trim();
    if (!text) return {};

    try {
        return JSON.parse(text);
    } catch {
        try {
            const jsonText = text
                .replace(/'([^'\\]*(?:\\.[^'\\]*)*)'/g, (_, value) => JSON.stringify(value.replace(/\\'/g, "'")))
                .replace(/\bTrue\b/g, 'true')
                .replace(/\bFalse\b/g, 'false')
                .replace(/\bNone\b/g, 'null');
            return JSON.parse(jsonText);
        } catch {
            return {};
        }
    }
}

function parseRecordModules(record, params = parseRecordParams(record)) {
    const raw = params.modules ?? record?.modules;
    if (Array.isArray(raw)) return raw.filter(item => item && typeof item === 'object');
    if (!raw) return [];
    if (typeof raw === 'object') return [raw];
    if (typeof raw !== 'string') return [];

    const text = raw.trim();
    if (!text || text === '-') return [];
    try {
        const parsed = JSON.parse(text);
        return Array.isArray(parsed) ? parsed.filter(item => item && typeof item === 'object') : [];
    } catch {
        const matches = text.match(/\{[^{}]*\}/g) || [];
        return matches.map(item => {
            try {
                return JSON.parse(item);
            } catch {
                return null;
            }
        }).filter(Boolean);
    }
}

function fileNameFromPath(path) {
    if (!path) return '';
    return String(path).split(/[\\/]/).filter(Boolean).pop() || '';
}

function normalizeUpdateRecord(record, index) {
    const params = parseRecordParams(record);
    const modules = parseRecordModules(record, params);
    const seafilePath = pick(record, 'seafile_path', '-');
    const status = statusMap(record.pack_status);
    return {
        raw: record,
        index,
        params,
        modules,
        status,
        createdTime: pick(record, 'created_time', '-'),
        supportCpu: pick(record, 'support_cpu', '-'),
        packageName: pick(record, 'package_name', 'name', 'file_name', 'filename') || fileNameFromPath(record.storage_path) || '包名称缺失',
        fileMd5: pick(record, 'fileMD5', 'file_md5', 'md5', 'filemd5', '-'),
        builder: pick(record.creator || {}, 'username', '-'),
        downloadPath: pick(record, 'download_path', ''),
        seafilePath,
        hasSeafile: Boolean(seafilePath && seafilePath !== '-'),
        storagePath: pick(record, 'storage_path', ''),
        recordId: pick(record, 'id', 'pk'),
        offline: formatOffline(params.offline ?? record.offline_status ?? record.offline),
        namespace: String(params.namespace ?? pick(record, 'namespace', '-')),
        supportOs: formatMaybeList(valueOrFallback(params.support_os, record.support_os)),
        platform: formatMaybeList(valueOrFallback(params.platform, record.platform)),
        seafile: String(params.seafile ?? record.seafile ?? '-'),
    };
}

function renderArtifactCard(record, packageType = state.currentRecordType) {
    const canUpload = isSeafileUploadAllowed(packageType);
    return `
        <article class="record-card artifact-card" data-index="${record.index}" data-storage="${escapeHtml(record.storagePath)}" data-record-id="${escapeHtml(record.recordId)}">
            <div class="artifact-summary">
                <span class="artifact-tag ${record.status.className}">${escapeHtml(record.status.label)}</span>
                <div class="artifact-main">
                    <div class="artifact-name" title="${escapeHtml(record.packageName)}">${escapeHtml(record.packageName)}</div>
                    <div class="artifact-subline">
                        <span>打包人：${escapeHtml(record.builder)}</span>
                        <span>模块数：${record.modules.length}</span>
                    </div>
                </div>
                <span class="artifact-cpu">${escapeHtml(record.supportCpu)}</span>
                <span class="artifact-time">${escapeHtml(record.createdTime)}</span>
                <div class="artifact-actions">
                    <button class="btn btn-sm btn-danger delete-record-btn" ${record.recordId ? '' : 'disabled'}>删除</button>
                </div>
            </div>
            <div class="artifact-addresses">
                <div class="artifact-address-row">
                    <span class="address-label">内网地址</span>
                    <span class="address-value" title="${escapeHtml(record.downloadPath || '-')}">${escapeHtml(record.downloadPath || '-')}</span>
                    <button class="btn btn-sm copy-intranet-btn" ${record.downloadPath ? '' : 'disabled'}>复制</button>
                </div>
                <div class="artifact-address-row">
                    <span class="address-label">云盘地址</span>
                    <span class="address-value" title="${escapeHtml(record.hasSeafile ? record.seafilePath : '暂无云盘地址')}">${escapeHtml(record.hasSeafile ? record.seafilePath : '暂无云盘地址')}</span>
                    ${record.hasSeafile
                        ? '<button class="btn btn-sm copy-extranet-btn">复制</button>'
                        : (canUpload ? '<button class="btn btn-sm upload-seafile-btn">上传云盘</button>' : '')}
                </div>
            </div>
            <div class="upload-progress" style="display:none">
                <div class="progress-bar"><div class="progress-fill"></div></div>
                <span class="progress-text muted">等待上传</span>
            </div>
            <div class="artifact-expand hidden">
                <div class="artifact-section-head">
                    <strong>包含模块（${record.modules.length}）</strong>
                    <span>分支 / 配置中心 / 详情</span>
                </div>
                ${renderArtifactModules(record)}
                <details class="artifact-basic">
                    <summary>基础信息</summary>
                    <div class="record-info-grid">
                        <span>适配架构</span><strong>${escapeHtml(record.supportCpu)}</strong>
                        <span>命名空间</span><strong>${escapeHtml(record.namespace)}</strong>
                        <span>操作系统</span><strong>${escapeHtml(record.supportOs)}</strong>
                        <span>平台</span><strong>${escapeHtml(record.platform)}</strong>
                        <span>离线类型</span><strong>${escapeHtml(record.offline)}</strong>
                        <span>网盘状态</span><strong>${escapeHtml(record.seafile)}</strong>
                        <span>文件校验值</span><strong>${escapeHtml(record.fileMd5)}</strong>
                        <span>打包人</span><strong>${escapeHtml(record.builder)}</strong>
                    </div>
                </details>
            </div>
        </article>
    `;
}

function renderArtifactModules(record) {
    if (!record.modules.length) {
        return '<div class="module-empty">暂无模块信息</div>';
    }
    return `
        <div class="artifact-module-list">
            ${record.modules.map((mod, moduleIndex) => {
                const apollo = apolloStatus(mod.need_apollo);
                const serviceName = pick(mod, 'name', 'custom_name', 'service_name', 'module_name', '-');
                const branch = pick(mod, 'ref_name', 'branch', 'tag', 'git_branch', '-');
                return `
                    <button class="artifact-module-card" type="button" data-record-index="${record.index}" data-module-index="${moduleIndex}">
                        <div class="module-form-row">
                            <span>服务名称：</span><strong title="${escapeHtml(serviceName)}">${escapeHtml(serviceName)}</strong>
                        </div>
                        <div class="module-form-row">
                            <span>版本分支：</span><b title="${escapeHtml(branch)}">${escapeHtml(branch)}</b>
                        </div>
                        <div class="module-form-row">
                            <span>配置中心：</span><b class="apollo-value ${apollo.className}">${escapeHtml(apollo.label.replace('配置中心：', ''))}</b>
                        </div>
                    </button>
                `;
            }).join('')}
        </div>
    `;
}

function apolloStatus(value) {
    const enabled = value === true || value === 1 || value === '1' || value === 'true' || value === 'True';
    const disabled = value === false || value === 0 || value === '0' || value === 'false' || value === 'False';
    if (enabled) return { label: '配置中心：已启用', className: 'enabled' };
    if (disabled) return { label: '配置中心：未启用', className: 'disabled' };
    return { label: `配置中心：${String(value ?? '-')}`, className: 'unknown' };
}

function formatMaybeList(value) {
    if (Array.isArray(value)) return value.length ? value.join(', ') : '-';
    if (value === null || value === undefined || value === '') return '-';
    return String(value);
}

function valueOrFallback(value, fallback) {
    if (Array.isArray(value) && !value.length) return fallback;
    if (value === null || value === undefined || value === '') return fallback;
    return value;
}

function formatOffline(value) {
    if (value === true || value === 1 || value === '1' || value === 'true' || value === 'True') return '离线';
    if (value === false || value === 0 || value === '0' || value === 'false' || value === 'False') return '在线';
    return String(value ?? '-');
}

function toggleArtifactDetail(card) {
    if (!card) return;
    const detail = card.querySelector('.artifact-expand');
    const open = detail.classList.toggle('hidden') === false;
    card.classList.toggle('expanded', open);
}

async function deletePackageRecord(card, btn, record, packageType = state.currentRecordType) {
    const recordId = pick(record || {}, 'id', 'pk') || card.dataset.recordId;
    if (!recordId) {
        showError('删除失败', '当前打包记录缺少 id/pk 字段。');
        return false;
    }
    if (!window.confirm('确认删除这条打包记录？')) return false;

    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '删除中...';
    try {
        await ApiClient.deletePackageRecord(packageType.family, recordId);
        card.remove();
        showSuccess('删除成功', '打包记录已删除。');
        return true;
    } catch (err) {
        btn.disabled = false;
        btn.textContent = originalText;
        showRequestError('删除失败', err);
        return false;
    }
}

function statusMap(status) {
    const map = {
        0: { key: 'building', label: '打包中', className: 'tag-building' },
        1: { key: 'success', label: '成功', className: 'tag-success' },
        2: { key: 'failed', label: '失败', className: 'tag-failed' },
        3: { key: 'building', label: '打包中', className: 'tag-building' },
    };
    return map[status] ?? { key: 'unknown', label: String(status ?? '-'), className: 'tag-pending' };
}

function openModuleDrawer(record, mod) {
    if (!record || !mod) return;
    const drawer = document.getElementById('moduleDrawer');
    const title = document.getElementById('moduleDrawerTitle');
    const content = document.getElementById('moduleDrawerContent');
    const serviceName = pick(mod, 'name', 'custom_name', 'service_name', 'module_name', '-');

    title.textContent = serviceName;
    content.innerHTML = `
        <div class="drawer-package">${escapeHtml(record.packageName)}</div>
        <div class="module-detail-grid">
            ${moduleDetailRows(mod, record).map(row => `
                <div class="detail-label">${escapeHtml(row.label)}</div>
                <div class="detail-value">${formatDetailValue(row.value)}</div>
            `).join('')}
        </div>
    `;
    drawer.classList.remove('hidden');
}

function closeModuleDrawer() {
    const drawer = document.getElementById('moduleDrawer');
    if (drawer) drawer.classList.add('hidden');
}

function moduleDetailRows(mod, record) {
    return [
        ['服务名称', pick(mod, 'name', 'custom_name', 'service_name', 'module_name', '-')],
        ['模块ID', pick(mod, 'pk', 'id', '-')],
        ['代码仓库', moduleGitUrl(mod) || pick(mod, 'git_repository', 'repo', 'repository_url', '-')],
        ['代码分支', pick(mod, 'ref_name', 'branch', 'tag', 'git_branch', '-')],
        ['提交版本', pick(mod, 'commit', 'commit_id', 'git_commit', 'sha', '-')],
        ['镜像名称', pick(mod, 'docker_image', 'image', 'image_name', '-')],
        ['镜像标签', pick(mod, 'docker_tag', 'image_tag', 'tag', '-')],
        ['镜像仓库地址', pick(mod, 'harbor', 'harbor_url', 'image_repo', '-')],
        ['配置中心', apolloStatus(mod.need_apollo).label],
        ['环境', pick(mod, 'env', 'environment', 'deploy_env') || record?.params?.namespace || '-'],
        ['发布说明', pick(mod, 'release_note', 'changelog', 'description', '-')],
        ['构建日志', pick(mod, 'build_log', 'log_url', 'ci_log', '-')],
        ['流水线', pick(mod, 'pipeline', 'pipeline_url', 'ci_pipeline', '-')],
        ['依赖', mod.dependencies ?? mod.deps ?? '-'],
    ].map(([label, value]) => ({ label, value }));
}

function formatDetailValue(value) {
    if (Array.isArray(value)) {
        return value.length ? escapeHtml(value.map(item => typeof item === 'object' ? JSON.stringify(item) : String(item)).join(', ')) : '-';
    }
    if (value && typeof value === 'object') {
        return `<pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre>`;
    }
    const text = String(value ?? '-');
    if (/^https?:\/\//.test(text)) {
        return `<a href="${escapeHtml(text)}" target="_blank" rel="noreferrer">${escapeHtml(text)}</a>`;
    }
    return escapeHtml(text || '-');
}

async function uploadToSeafile(card, btn, record, storagePath) {
    btn.disabled = true;
    btn.textContent = '上传中...';
    card.querySelector('.upload-progress').style.display = '';

    try {
        const result = await ApiClient.uploadToSeafile(storagePath);
        const taskId = result.taskID || result.task_id;
        if (!result.success || !taskId) {
            throw new Error(result.message || '上传任务创建失败。');
        }

        state.uploadTasks[String(taskId)] = { card, record };
        startUploadPolling();
        card.querySelector('.progress-text').textContent = '上传任务已触发...';
        showInfo('上传已触发', `任务 ID：${taskId}`);
    } catch (err) {
        showRequestError('上传云盘失败', err);
        btn.disabled = false;
        btn.textContent = '上传云盘';
        card.querySelector('.upload-progress').style.display = 'none';
    }
}

function formatUploadProgress(progress) {
    const speed = progress.speed ? ` · ${progress.speed}` : '';
    return `${progress.description || '上传中'}：${progress.percent || 0}%${speed}`;
}

function startUploadPolling() {
    if (state.uploadTimer) return;
    state.uploadTimer = setInterval(pollUploadProgress, 2000);
}

function stopUploadPolling() {
    if (state.uploadTimer) {
        clearInterval(state.uploadTimer);
        state.uploadTimer = null;
    }
}

async function pollUploadProgress() {
    const taskIds = Object.keys(state.uploadTasks);
    if (!taskIds.length) {
        stopUploadPolling();
        return;
    }

    for (const taskId of taskIds) {
        try {
            const result = await ApiClient.getUploadProgress(taskId);
            const entry = state.uploadTasks[taskId];
            if (!entry || !entry.card) continue;

            const progress = result.progress || {};
            const fill = entry.card.querySelector('.progress-fill');
            const text = entry.card.querySelector('.progress-text');
            if (fill && progress.percent !== undefined) {
                fill.style.width = Math.min(100, Math.max(0, Number(progress.percent) || 0)) + '%';
            }
            if (text && progress.description) {
                text.textContent = formatUploadProgress(progress);
            }

            if (result.complete) {
                const success = !!result.success;
                if (fill) fill.style.width = success ? '100%' : fill.style.width;
                if (text) text.textContent = success ? '上传完成' : '上传失败';
                delete state.uploadTasks[taskId];
                if (success) {
                    showSuccess('上传完成', '网盘上传任务已完成。');
                    await loadPackageRecords();
                } else {
                    showError('上传失败', '网盘上传任务执行失败。');
                }
            }
        } catch {
            // 单次轮询失败不中断整体
        }
    }

    if (!Object.keys(state.uploadTasks).length) {
        stopUploadPolling();
    }
}

/* ================================================================
 * 提交打包
 * ================================================================ */

function renderPackConfirmationItems(modules) {
    return modules.map(module => {
        const name = escapeHtml(pick(module, 'custom_name', 'name', 'module_name', '未命名组件'));
        const branch = escapeHtml(pick(module, 'ref_name', 'branch', 'git_branch', 'tag', '-'));
        return `<li class="pack-confirm-item"><span>${name}</span><code>${branch}</code></li>`;
    }).join('');
}

function alignPackConfirmationNames(body) {
    const names = [...body.querySelectorAll('.pack-confirm-item > span')];
    const maxWidth = Math.max(...names.map(name => name.scrollWidth), 0);
    body.style.setProperty('--pack-confirm-name-width', `${maxWidth}px`);
}

function showPackageFamilySelection(payload) {
    const overlay = document.getElementById('modalOverlay');
    const body = document.getElementById('modalBody');
    const defaults = getDefaultPackParameters();
    body.className = 'modal-body pack-confirm-modal';
    body.innerHTML = `
        <h3>打包参数</h3>
        <div class="form-card pack-parameter-form">
            <div class="form-row"><span class="label">包类型</span>
                <select id="packageFamilySelect" class="form-select">
                    <option value="install">安装包</option><option value="upgrade">升级包</option>
                </select>
            </div>
            <div class="form-row"><span class="label">网络类型</span>
                <select id="packageNetworkSelect" class="form-select">
                    <option value="offline">离线</option><option value="online">在线</option>
                </select>
            </div>
            <div class="form-row"><span class="label">CPU 架构</span>
                <select id="packageCpuSelect" class="form-select">
                    <option value="x86_64">x86_64</option><option value="aarch64">aarch64</option>
                </select>
            </div>
            <div class="form-row"><span class="label">命名空间</span>
                <input id="packageNamespaceInput" class="form-input" value="${defaults.namespace}">
            </div>
            <div class="form-row"><span class="label">上传云盘</span>
                <span id="packageSeafileToggleWrap" class="toggle-wrap"><label class="toggle-track">
                    <input type="checkbox" id="packageSeafileToggle">
                </label></span>
            </div>
        </div>
        <div class="modal-actions">
            <button type="button" class="btn btn-secondary" id="packageFamilyCancel">取消</button>
            <button type="button" class="btn btn-primary" id="packageParameterNext">下一步</button>
        </div>
    `;
    overlay.style.display = 'flex';
    document.getElementById('packageFamilyCancel').onclick = closeModal;
    const networkSelect = document.getElementById('packageNetworkSelect');
    const seafileToggle = document.getElementById('packageSeafileToggle');
    const seafileWrap = document.getElementById('packageSeafileToggleWrap');
    const syncSeafile = () => {
        const enabled = networkSelect.value === 'offline';
        seafileToggle.disabled = !enabled;
        if (!enabled) seafileToggle.checked = false;
        seafileWrap.classList.toggle('toggle-disabled', !enabled);
    };
    networkSelect.onchange = syncSeafile;
    syncSeafile();
    document.getElementById('packageParameterNext').onclick = () => {
        const family = document.getElementById('packageFamilySelect').value;
        const offline = networkSelect.value === 'offline';
        const packageType = getPackageType(family, offline);
        showPackConfirmation({
            ...payload,
            packageType,
            offline: offline ? 1 : 0,
            support_cpu: document.getElementById('packageCpuSelect').value,
            namespace: document.getElementById('packageNamespaceInput').value.trim() || defaults.namespace,
            seafile: isSeafileUploadAllowed(packageType) && seafileToggle.checked,
        });
    };
}

function showPackConfirmation(payload) {
    const overlay = document.getElementById('modalOverlay');
    const body = document.getElementById('modalBody');
    body.className = 'modal-body pack-confirm-modal';
    body.innerHTML = `
        <h3>确认开始打包</h3>
        <p class="muted">包类型：${escapeHtml(payload.packageType.label)}</p>
        <p class="muted">网络类型：${payload.packageType.offline ? '离线' : '在线'}　CPU 架构：${escapeHtml(payload.support_cpu)}　命名空间：${escapeHtml(payload.namespace)}　上传云盘：${payload.seafile ? '是' : '否'}</p>
        <p class="muted">请确认以下组件及分支，确认后将提交打包任务。</p>
        <ul class="pack-confirm-list">${renderPackConfirmationItems(payload.modules)}</ul>
        <div class="modal-actions">
            <button type="button" class="btn btn-secondary" id="packConfirmCancel">取消</button>
            <button type="button" class="btn btn-primary" id="packConfirmSubmit">确认打包</button>
        </div>
    `;
    overlay.style.display = 'flex';
    alignPackConfirmationNames(body);
    document.getElementById('packConfirmCancel').onclick = closeModal;
    document.getElementById('packConfirmSubmit').onclick = () => {
        closeModal();
        executePack(payload);
    };
}

function submitPack() {
    if (!state.currentVersion) {
        showError('无法打包', '请先选择一个版本。');
        return;
    }

    const payload = buildPackPayload();
    if (!payload.modules.length) {
        showError('无法打包', '请至少勾选一个业务组件。');
        return;
    }

    showPackageFamilySelection(payload);
}

async function executePack(payload) {
    const versionId = objectId(state.currentVersion);
    const btn = document.getElementById('packButton');
    btn.disabled = true;
    btn.textContent = '正在提交...';
    setRightPanelLoading(true, '正在提交打包...');

    try {
        const { packageType, ...requestPayload } = payload;
        const result = await ApiClient.submitPackage(packageType.family, versionId, requestPayload);
        const message = pick(result, 'msg', 'message', 'detail', '打包任务已提交。');
        showSuccess('提交成功', message);
        selectPackageRecordType(packageType);
        await loadPackageRecords();
    } catch (err) {
        showRequestError('提交打包失败', err);
    } finally {
        btn.disabled = false;
        btn.textContent = '开始打包';
        setRightPanelLoading(false);
    }
}
function buildPackPayload() {
    const rows = document.querySelectorAll('#moduleList .module-row');

    const modules = [];
    rows.forEach(row => {
        const cb = row.querySelector('.module-checkbox');
        if (!cb || !cb.checked) return;
        const mod = state.moduleRows[Number(row.dataset.index)];
        if (!mod) return;
        modules.push({
            need_apollo: true,
            ref_name: pick(mod, 'branch', 'ref_name', 'git_branch', 'tag'),
            pk: mod.pk ?? mod.id,
            name: pick(mod, 'name', 'module_name'),
            custom_name: pick(mod, 'name', 'module_name'),
        });
    });

    return {
        modules: modules,
    };
}

/* ================================================================
 * 弹窗
 * ================================================================ */

function closeModal() {
    document.getElementById('modalOverlay').style.display = 'none';
    document.getElementById('modalBody').className = 'modal-body';
}

/* ================================================================
 * 三栏拖拽
 * ================================================================ */

const splitterState = {
    minWidths: [260, 280, 420],
    widths: null,
    drag: null,
};

function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
}

function getSplitterPanels() {
    return [...document.querySelectorAll('.splitter-panel')];
}

function measureSplitterColumns() {
    const panels = getSplitterPanels();
    const widths = panels.map(panel => panel.getBoundingClientRect().width);
    if (widths.length !== 3 || widths.some(width => width <= 0)) return;
    splitterState.widths = widths;
    applySplitterColumns(splitterState.widths);
}

function applySplitterColumns(widths) {
    const splitter = document.querySelector('.splitter');
    if (!splitter || widths.length !== 3) return;
    splitter.style.setProperty('--split-col-1', `${Math.round(widths[0])}px`);
    splitter.style.setProperty('--split-col-2', `${Math.round(widths[1])}px`);
    splitter.style.setProperty('--split-col-3', `${Math.round(widths[2])}px`);
}

function resizeSplitterPair(handleIndex, delta) {
    const widths = splitterState.widths || getSplitterPanels().map(panel => panel.getBoundingClientRect().width);
    const leftIndex = handleIndex;
    const rightIndex = handleIndex + 1;
    const total = widths[leftIndex] + widths[rightIndex];
    const nextLeft = clamp(
        widths[leftIndex] + delta,
        splitterState.minWidths[leftIndex],
        total - splitterState.minWidths[rightIndex],
    );

    const next = [...widths];
    next[leftIndex] = nextLeft;
    next[rightIndex] = total - nextLeft;
    splitterState.widths = next;
    applySplitterColumns(next);
}

function initResizableSplitter() {
    const splitter = document.querySelector('.splitter');
    const handles = [...document.querySelectorAll('.splitter-handle')];
    if (!splitter || handles.length !== 2) return;

    measureSplitterColumns();

    handles.forEach(handle => {
        const handleIndex = Number(handle.dataset.handle);

        handle.addEventListener('pointerdown', (event) => {
            event.preventDefault();
            measureSplitterColumns();
            splitterState.drag = {
                handleIndex,
                startX: event.clientX,
                startWidths: [...splitterState.widths],
            };
            splitter.classList.add('dragging');
            handle.classList.add('active');
            document.body.classList.add('resizing-columns');
            handle.setPointerCapture(event.pointerId);
        });

        handle.addEventListener('keydown', (event) => {
            if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
            event.preventDefault();
            measureSplitterColumns();
            resizeSplitterPair(handleIndex, event.key === 'ArrowLeft' ? -24 : 24);
        });
    });

    window.addEventListener('pointermove', (event) => {
        if (!splitterState.drag) return;
        const { handleIndex, startX, startWidths } = splitterState.drag;
        splitterState.widths = [...startWidths];
        resizeSplitterPair(handleIndex, event.clientX - startX);
    });

    window.addEventListener('pointerup', () => {
        if (!splitterState.drag) return;
        splitterState.drag = null;
        splitter.classList.remove('dragging');
        handles.forEach(handle => handle.classList.remove('active'));
        document.body.classList.remove('resizing-columns');
    });

    window.addEventListener('resize', () => {
        splitterState.widths = null;
        measureSplitterColumns();
    });
}

/* ================================================================
 * 初始化
 * ================================================================ */

function initApp() {
    // 登录页事件
    document.getElementById('loginButton').onclick = doLogin;
    document.getElementById('loginPassword').onkeydown = (e) => {
        if (e.key === 'Enter') doLogin();
    };

    document.getElementById('userMenuTrigger').onclick = () => {
        const menu = document.getElementById('userMenu');
        setUserMenuOpen(!menu.classList.contains('open'));
    };
    document.getElementById('userProfileButton').onclick = () => {
        setUserMenuOpen(false);
        showUserProfile();
    };
    document.getElementById('logoutButton').onclick = logout;
    document.addEventListener('click', event => {
        if (!document.getElementById('userMenu').contains(event.target)) setUserMenuOpen(false);
    });

    // 搜索项目
    document.getElementById('projectSearch').oninput = debouncedSearch;
    document.getElementById('projectSearch').onkeydown = (e) => {
        if (e.key === 'Enter') loadProjects();
    };

    // 项目标签切换
    document.getElementById('pivotFav').onclick = () => switchProjectTab('favorite');
    document.getElementById('pivotAll').onclick = () => switchProjectTab('all');
    document.getElementById('projectPrevPage').onclick = () => goCurrentProjectPage(-1);
    document.getElementById('projectNextPage').onclick = () => goCurrentProjectPage(1);

    // 模块过滤
    document.getElementById('moduleSearch').oninput = filterModules;
    document.getElementById('selectAllCheckbox').onchange = (e) => selectAllModules(e.target.checked);

    // 打包
    document.getElementById('packButton').onclick = submitPack;
    document.getElementById('cancelButton').onclick = clearModules;

    // 弹窗关闭
    document.getElementById('modalOverlay').onclick = (e) => {
        if (e.target === document.getElementById('modalOverlay')) closeModal();
    };
    document.getElementById('modalCloseBtn').onclick = closeModal;

    initResizableSplitter();

    ApiClient.onAuthenticationFailure = handleSessionExpired;
    restoreSession();
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', initApp);
