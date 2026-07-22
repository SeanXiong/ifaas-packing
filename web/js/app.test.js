const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const elements = {
    seafileToggleWrap: { classList: new Set(['toggle-wrap', 'toggle-on']) },
    loginPage: { style: {} },
    mainPage: { style: {} },
    loginUsername: { value: '' },
    loginPassword: { value: '' },
    loginButton: { disabled: false, textContent: '登录' },
    loginRemember: { checked: false },
    projectSearch: { value: '' },
    favoriteList: { innerHTML: '' },
    allProjectList: { innerHTML: '', classList: new Set() },
    favoriteList: { innerHTML: '', classList: new Set() },
    pivotFav: { classList: new Set() },
    pivotAll: { classList: new Set() },
    projectPagination: { classList: new Set(['hidden']), style: {} },
    projectPageInfo: { textContent: '' },
    projectPrevPage: { disabled: false },
    projectNextPage: { disabled: false },
    rightPanelLoading: { classList: new Set(['hidden']) },
    rightPanelLoadingText: { textContent: '' },
    offlineRadio: { checked: false },
    onlineRadio: { checked: true },
    seafileToggle: { checked: true, disabled: false },
    cpuSelect: { value: 'x86_64' },
    namespaceInput: { value: 'basic-app' },
    apolloInput: { value: '' },
};
elements.seafileToggleWrap.classList.toggle = function (name, enabled) {
    if (enabled) this.add(name);
    else this.delete(name);
};for (const element of Object.values(elements)) {
    if (element.classList && !element.classList.toggle) {
        element.classList.toggle = function (name, enabled) {
            if (enabled) this.add(name);
            else this.delete(name);
        };
        element.classList.remove = function (name) {
            this.delete(name);
        };
    }
}

const context = {
    console,
    URLSearchParams,
    document: {
        addEventListener() {},
        getElementById(id) { return elements[id]; },
        querySelectorAll() { return []; },
    },
    requestAnimationFrame() {},
    setTimeout() {},
    clearTimeout() {},
    debounce(fn) { return fn; },
    sessionStorage: {
        values: new Map(),
        getItem(key) { return this.values.get(key) || null; },
        setItem(key, value) { this.values.set(key, String(value)); },
        removeItem(key) { this.values.delete(key); },
    },
    ApiClient: {
        token: null,
        searchProjects: async () => [],
        isAuthenticationError: error => Boolean(error && error.isAuthenticationError),
    },
    ConfigStore: {
        loadCredentials: async () => ({ username: '', password: '', remember: false }),
        loadFavorites: async () => new Set(),
    },
    showError() {},
    showSuccess() {},
    moduleId(data) { return String(data.pk || data.id || ''); },
    objectId(data) { return String(data.pk || data.id || ''); },
    escapeHtml(value) { return String(value); },
    pick(data, ...keys) {
        for (const key of keys) {
            if (data && data[key] !== undefined && data[key] !== null && data[key] !== '') return String(data[key]);
        }
        return '';
    },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(__dirname + '/app.js', 'utf8'), context);

const onlineInstallPackageType = vm.runInContext("getPackageType('install', false)", context);
assert.deepEqual(JSON.parse(JSON.stringify(onlineInstallPackageType)), {
    family: 'install',
    offline: false,
    label: '在线安装包',
    recordsPath: '/api/v1/recordsprojectinstall/',
});
assert.deepEqual(JSON.parse(JSON.stringify(vm.runInContext('state.currentRecordType', context))), {
    family: 'install',
    offline: true,
});
assert.deepEqual(JSON.parse(JSON.stringify(vm.runInContext('getDefaultPackParameters()', context))), {
    family: 'install',
    offline: true,
    support_cpu: 'x86_64',
    namespace: 'basic-app',
    seafile: false,
});
assert.equal(vm.runInContext("getLoginProfileName('?profile=alice')", context), 'alice');
assert.equal(vm.runInContext("getLoginProfileName('?profile=not%20valid')", context), '');
assert.equal(vm.runInContext("isSeafileUploadAllowed(getPackageType('upgrade', false))", context), false);
assert.equal(vm.runInContext("isSeafileUploadAllowed(getPackageType('install', true))", context), true);
assert.deepEqual(
    Array.from(vm.runInContext('getPackageTypeOptions()', context), item => item.label),
    ['离线升级包', '离线安装包', '在线升级包', '在线安装包'],
);
assert.deepEqual(JSON.parse(JSON.stringify(vm.runInContext('getPackageFamilies()', context))), [
    { value: 'upgrade', label: '升级包' },
    { value: 'install', label: '安装包' },
]);
assert.deepEqual(JSON.parse(JSON.stringify(vm.runInContext('getNetworkTypes()', context))), [
    { value: 'offline', label: '离线' },
    { value: 'online', label: '在线' },
]);
const parameterlessPayload = vm.runInContext('buildPackPayload()', context);
assert.deepEqual(JSON.parse(JSON.stringify(parameterlessPayload)), { modules: [] });
context.document.querySelectorAll = () => [{
    dataset: { index: '0' },
    querySelector() { return { checked: true }; },
}];
vm.runInContext("state.moduleRows = [{ id: 1, name: 'gateway', branch: 'release/1.0.0' }]", context);
const modulePayload = vm.runInContext('buildPackPayload()', context);
assert.equal(modulePayload.modules[0].need_apollo, true);
context.document.querySelectorAll = () => [];
assert.deepEqual(
    JSON.parse(JSON.stringify(vm.runInContext("selectPackageRecordType(getPackageType('install', false))", context))),
    { family: 'install', offline: false, label: '在线安装包', recordsPath: '/api/v1/recordsprojectinstall/' },
);
const onlineCard = vm.runInContext(`renderArtifactCard({
    index: 0, status: { className: '', label: '成功' }, packageName: 'online.tar.gz',
    builder: 'tester', modules: [], supportCpu: 'x86_64', createdTime: '-', recordId: 1,
    downloadPath: '', hasSeafile: false, seafilePath: '', storagePath: '/tmp/online.tar.gz',
    namespace: '-', supportOs: '-', platform: '-', offline: '在线', seafile: 'false', fileMd5: '-',
}, getPackageType('install', false))`, context);
assert.doesNotMatch(onlineCard, /upload-seafile-btn/);
const moduleCards = vm.runInContext(`renderArtifactModules({
    index: 0,
    modules: [{ id: 21790, name: 'gateway', ref_name: 'release/1.2.0', need_apollo: true }],
})`, context);
assert.match(moduleCards, /gateway/);
assert.match(moduleCards, /release\/1\.2\.0/);
assert.match(moduleCards, /配置中心：<\/span><b class="apollo-value enabled">已启用/);
assert.match(moduleCards, /服务名称/);
assert.match(moduleCards, /版本分支/);
assert.doesNotMatch(moduleCards, /21790/);
assert.equal(vm.runInContext("formatUploadProgress({ description: '上传中', percent: 5.3, speed: '67.09 MB/s' })", context), '上传中：5.3% · 67.09 MB/s');
console.log('PASS: package type maps installation and online state');

const indexHtml = fs.readFileSync(__dirname + '/../index.html', 'utf8');
assert.doesNotMatch(indexHtml, /id="seafileToggleWrap" class="[^"]*toggle-on/);
assert.doesNotMatch(indexHtml, /id="loginRemember"/);
assert.match(indexHtml, /<link rel="icon" type="image\/svg\+xml" href="favicon\.svg">/);
assert.match(indexHtml, /<script src="js\/utils\.js\?v=202607201910"><\/script>/);
assert.match(indexHtml, /<script src="js\/app\.js\?v=202607201910"><\/script>/);
assert.match(indexHtml, /id="userMenuTrigger"/);
assert.match(indexHtml, /id="logoutButton"/);
assert.doesNotMatch(indexHtml, /id="offlineRadio"/);
assert.doesNotMatch(indexHtml, /id="onlineRadio"/);
assert.doesNotMatch(indexHtml, /id="cpuSelect"/);
assert.doesNotMatch(indexHtml, /id="namespaceInput"/);
assert.doesNotMatch(indexHtml, /id="apolloInput"/);
assert.doesNotMatch(indexHtml, /id="seafileToggle"/);
assert.doesNotMatch(indexHtml, /id="packageFamilySelect"/);
assert.equal(fs.existsSync(__dirname + '/../favicon.svg'), true);
const appCss = fs.readFileSync(__dirname + '/../css/app.css', 'utf8');
const appJs = fs.readFileSync(__dirname + '/app.js', 'utf8');
assert.equal((appJs.match(/id="recordsClose"/g) || []).length, 0);
assert.equal((appJs.match(/id="recordsCloseTop"/g) || []).length, 1);
assert.doesNotMatch(appCss, /\.branch-select:focus-within\s+\.branch-options/);
assert.doesNotMatch(appJs, /function syncSeafileAvailability\(/);
assert.doesNotMatch(appJs, /function syncSeafileToggle\(/);
assert.match(appCss, /\.pack-confirm-item\s*\{[\s\S]*?grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
assert.match(appCss, /\.pack-confirm-item code\s*\{[\s\S]*?text-align:\s*left/);
assert.match(appCss, /\.pack-parameter-form\s*\{[\s\S]*?grid-template-columns:\s*88px 240px/);
assert.match(appCss, /\.pack-parameter-form \.label\s*\{[\s\S]*?text-align:\s*right/);
assert.match(appCss, /\.pack-parameter-form \.form-input,[\s\S]*?\.pack-parameter-form \.form-select\s*\{[\s\S]*?width:\s*240px/);
assert.match(appJs, /id="packageNetworkSelect"/);
assert.match(appJs, /id="packageCpuSelect"/);
assert.match(appJs, /id="packageNamespaceInput"/);
assert.match(appJs, /need_apollo:\s*true/);

console.log('PASS: package parameter controls are scoped to the modal');

vm.runInContext("setRightPanelLoading(true, '正在提交打包...')", context);
assert.equal(elements.rightPanelLoading.classList.has('hidden'), false);
assert.equal(elements.rightPanelLoadingText.textContent, '正在提交打包...');
vm.runInContext('setRightPanelLoading(false)', context);
assert.equal(elements.rightPanelLoading.classList.has('hidden'), true);
console.log('PASS: right panel loading overlay toggles with status text');

const favoritePage = vm.runInContext(
    'paginateProjects(Array.from({ length: 21 }, (_, index) => ({ id: index + 1 })), 2, 20)',
    context,
);
assert.deepEqual(Array.from(favoritePage, project => project.id), [21]);
console.log('PASS: favorite projects use local pagination');

(async () => {
    context.sessionStorage.setItem('ifaas-packing.token', 'cached-token');
    context.sessionStorage.setItem('ifaas-packing.username', 'cached-user');
    await vm.runInContext('restoreSession()', context);
    assert.equal(context.ApiClient.token, 'cached-token');
    assert.equal(elements.loginPage.style.display, 'none');
    assert.equal(elements.mainPage.style.display, 'flex');

    vm.runInContext('handleSessionExpired()', context);
    assert.equal(context.sessionStorage.getItem('ifaas-packing.token'), null);
    assert.equal(context.sessionStorage.getItem('ifaas-packing.username'), null);
    assert.equal(context.ApiClient.token, null);
    assert.equal(elements.loginPage.style.display, 'flex');
    assert.equal(elements.mainPage.style.display, 'none');
    console.log('PASS: session Token restores and expires in the current tab');

    let credentialReads = 0;
    context.ConfigStore.loadCredentials = async () => {
        credentialReads++;
        return { username: 'another-user', password: 'secret', remember: true };
    };
    elements.loginUsername.value = 'previous-user';
    elements.loginPassword.value = 'previous-password';
    await vm.runInContext('showLoginPage()', context);
    assert.equal(credentialReads, 0);
    assert.equal(elements.loginUsername.value, '');
    assert.equal(elements.loginPassword.value, '');
    console.log('PASS: login page never restores another user credentials');

    let savedProfile = null;
    const realLoadFavoriteProjects = context.loadFavoriteProjects;
    context.ApiClient.init = () => {};
    context.ApiClient.login = async () => { context.ApiClient.token = 'new-token'; };
    context.ConfigStore.saveLoginProfile = async (username, password) => {
        savedProfile = { username, password };
    };
    context.loadFavoriteProjects = async () => {};
    context.showInfo = () => {};
    elements.loginUsername.value = 'alice';
    elements.loginPassword.value = 'alice-password';
    await vm.runInContext('doLogin()', context);
    assert.deepEqual(savedProfile, { username: 'alice', password: 'alice-password' });
    assert.equal(elements.mainPage.style.display, 'flex');
    context.loadFavoriteProjects = realLoadFavoriteProjects;
    console.log('PASS: successful login saves the current profile');

    const requestedPages = [];
    const favoriteAccounts = [];
    let favoriteProjectRequests = 0;
    context.ConfigStore.loadFavoriteProjects = async username => {
        favoriteAccounts.push(username);
        return [];
    };
    context.ApiClient.getProject = async () => {
        favoriteProjectRequests++;
        return null;
    };
    context.ApiClient.getProjectsPage = async (keyword, page) => {
        requestedPages.push(page);
        return { projects: [], page, pageSize: 20, count: 40 };
    };
    vm.runInContext("state.currentUsername = 'alice'", context);
    await vm.runInContext('loadFavoriteProjects()', context);
    assert.equal(favoriteProjectRequests, 0);
    assert.deepEqual(favoriteAccounts, ['alice']);
    assert.deepEqual(requestedPages, []);
    assert.equal(elements.projectPagination.classList.has('hidden'), false);

    await vm.runInContext("switchProjectTab('all')", context);
    assert.deepEqual(requestedPages, [1]);
    await vm.runInContext('loadProjectPage(2)', context);
    assert.deepEqual(requestedPages, [1, 2]);
    console.log('PASS: full projects load page by page only after opening the all-projects tab');

    let updatedModuleId = null;
    let updatedPayload = null;
    context.ApiClient.getGitConfig = async () => {
        throw new Error('确认修改时不应查询 git_config');
    };
    context.ApiClient.updateModule = async (moduleId, payload) => {
        updatedModuleId = moduleId;
        updatedPayload = payload;
        return {
            id: 21790,
            name: 'etl-vedio-structure-mq',
            custom_name: 'etl-vedio-structure-mq',
            service_type: 1,
            branch: 'rel_1.6.2_DeepSea_hotfix_tianfu',
            APP_ID: 'etl-vedio-structure-mq',
            git_config_path: 'build_ci/config.yml',
            is_image: true,
            version: 1734,
            git_url: 154,
        };
    };
    const module = {
        id: 21790,
        name: 'etl-vedio-structure-mq',
        custom_name: 'etl-vedio-structure-mq',
        service_type: { id: '1', name: '普通服务' },
        APP_ID: 'etl-vedio-structure-mq',
        git_config_path: 'build_ci/config.yml',
        is_image: true,
        git_url: 1132,
    };
    const branchText = { textContent: '' };
    const moduleRow = { querySelector: selector => selector === '.branch-text' ? branchText : null };
    context.testModule = module;
    context.testModuleRow = moduleRow;
    vm.runInContext('state.currentVersion = { id: 1734 }', context);
    await vm.runInContext(
        "updateModuleBranch(testModule, testModuleRow, 'ignored-git-url', 'rel_1.6.2_DeepSea_hotfix_tianfu', { git_id: 1132 })",
        context,
    );
    assert.equal(updatedModuleId, '21790');
    assert.deepEqual(JSON.parse(JSON.stringify(updatedPayload)), {
        name: 'etl-vedio-structure-mq',
        custom_name: 'etl-vedio-structure-mq',
        service_type: 1,
        branch: 'rel_1.6.2_DeepSea_hotfix_tianfu',
        APP_ID: 'etl-vedio-structure-mq',
        git_config_path: 'build_ci/config.yml',
        is_image: true,
        version: '1734',
        git_url: 1132,
    });
    assert.equal(module.git_url, 154);
    assert.equal(branchText.textContent, 'rel_1.6.2_DeepSea_hotfix_tianfu');
    console.log('PASS: module branch update sends the module ID and applies the API response');

    const branchConfirmButton = { disabled: false, textContent: '确认修改' };
    const branchCancelButton = { disabled: false };
    context.testBranchConfirmButton = branchConfirmButton;
    context.testBranchCancelButton = branchCancelButton;
    vm.runInContext('setBranchSaveLoading(testBranchConfirmButton, testBranchCancelButton, true)', context);
    assert.equal(branchConfirmButton.disabled, true);
    assert.equal(branchCancelButton.disabled, true);
    assert.equal(branchConfirmButton.textContent, '正在保存...');
    vm.runInContext('setBranchSaveLoading(testBranchConfirmButton, testBranchCancelButton, false)', context);
    assert.equal(branchConfirmButton.disabled, false);
    assert.equal(branchCancelButton.disabled, false);
    assert.equal(branchConfirmButton.textContent, '确认修改');
    console.log('PASS: branch save keeps the dialog controls in a loading state');

    const confirmationItems = vm.runInContext(`renderPackConfirmationItems([
        { name: 'gateway', ref_name: 'release/1.2.0' },
        { custom_name: 'etl', branch: 'hotfix/42' },
    ])`, context);
    assert.match(confirmationItems, /gateway/);
    assert.match(confirmationItems, /release\/1\.2\.0/);
    assert.match(confirmationItems, /etl/);
    assert.match(confirmationItems, /hotfix\/42/);
    console.log('PASS: pack confirmation lists each selected module and branch');
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
