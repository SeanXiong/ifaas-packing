const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const elements = {
    seafileToggleWrap: { classList: new Set(['toggle-wrap', 'toggle-on']) },
    loginPage: { style: {} },
    mainPage: { style: {} },
    loginUsername: { value: '' },
    loginPassword: { value: '' },
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
    document: {
        addEventListener() {},
        getElementById(id) { return elements[id]; },
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
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(__dirname + '/app.js', 'utf8'), context);

vm.runInContext('syncSeafileToggle(false)', context);
assert.equal(elements.seafileToggleWrap.classList.has('toggle-on'), false);

const indexHtml = fs.readFileSync(__dirname + '/../index.html', 'utf8');
assert.doesNotMatch(indexHtml, /id="seafileToggleWrap" class="[^"]*toggle-on/);
assert.match(indexHtml, /<link rel="icon" type="image\/svg\+xml" href="favicon\.svg">/);
assert.equal(fs.existsSync(__dirname + '/../favicon.svg'), true);

console.log('PASS: Seafile toggle starts and synchronizes as disabled');

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
    await vm.runInContext('restoreSession()', context);
    assert.equal(context.ApiClient.token, 'cached-token');
    assert.equal(elements.loginPage.style.display, 'none');
    assert.equal(elements.mainPage.style.display, 'flex');

    vm.runInContext('handleSessionExpired()', context);
    assert.equal(context.sessionStorage.getItem('ifaas-packing.token'), null);
    assert.equal(context.ApiClient.token, null);
    assert.equal(elements.loginPage.style.display, 'flex');
    assert.equal(elements.mainPage.style.display, 'none');
    console.log('PASS: session Token restores and expires in the current tab');

    const requestedPages = [];
    let favoriteProjectRequests = 0;
    context.ConfigStore.loadFavorites = async () => new Set(['1', '2']);
    context.ApiClient.getProject = async () => {
        favoriteProjectRequests++;
        return null;
    };
    context.ApiClient.getProjectsPage = async (keyword, page) => {
        requestedPages.push(page);
        return { projects: [], page, pageSize: 20, count: 40 };
    };
    await vm.runInContext('loadFavoriteProjects()', context);
    assert.equal(favoriteProjectRequests, 2);
    assert.deepEqual(requestedPages, []);
    assert.equal(elements.projectPagination.classList.has('hidden'), false);

    await vm.runInContext("switchProjectTab('all')", context);
    assert.deepEqual(requestedPages, [1]);
    await vm.runInContext('loadProjectPage(2)', context);
    assert.deepEqual(requestedPages, [1, 2]);
    console.log('PASS: full projects load page by page only after opening the all-projects tab');
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});