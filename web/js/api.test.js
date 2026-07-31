const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const context = {
    console,
    URL,
    URLSearchParams,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(__dirname + '/api.js', 'utf8'), context);

async function testGetProjectsPageRequestsOnlyOnePage() {
    const requestedUrls = [];
    context.fetch = async (url) => {
        requestedUrls.push(url);
        const params = new URL(url, 'http://localhost').searchParams;
        const page = params.get('page');
        assert.equal(params.get('pageSize'), '20');
        assert.equal(page, '1');
        const data = {
            page: 1,
            pageSize: 20,
            count: 7,
            results: [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }, { id: 5 }],
        };
        return {
            ok: true,
            text: async () => JSON.stringify(data),
        };
    };

    const result = await vm.runInContext('ApiClient.getProjectsPage()', context);

    assert.deepEqual(Array.from(result.projects, project => project.id), [1, 2, 3, 4, 5]);
    assert.equal(result.count, 7);
    assert.equal(requestedUrls.length, 1);
}

async function testInvalidTokenResponseIsAuthenticationError() {
    context.fetch = async () => ({
        ok: true,
        status: 200,
        text: async () => JSON.stringify({ detail: 'Invalid token.', errorCode: '200401' }),
    });

    await assert.rejects(
        () => vm.runInContext("ApiClient._request('GET', '/api/v1/project/?page=1')", context),
        error => error.isAuthenticationError === true,
    );
}

async function testInstallationPackageUsesInstallationResources() {
    const requests = [];
    context.fetch = async (url, options) => {
        requests.push({ url, options });
        return {
            ok: true,
            text: async () => JSON.stringify({ results: [] }),
        };
    };

    await vm.runInContext("ApiClient.getPackageRecords('install', 2451, false)", context);
    await vm.runInContext("ApiClient.deletePackageRecord('install', 19390)", context);
    await vm.runInContext("ApiClient.submitPackage('install', 2451, { offline: 0 })", context);

    assert.match(requests[0].url, /\/api\/v1\/recordsprojectinstall\/\?version_id=2451&offline_status=False$/);
    assert.equal(requests[1].url, '/api/proxy/api/v1/recordsprojectinstall/19390');
    assert.equal(requests[1].options.method, 'DELETE');
    assert.equal(requests[2].url, '/api/proxy/api/v1/packplus/install/2451');
    assert.equal(JSON.parse(requests[2].options.body).offline, 0);
}

async function testLogoutUsesDocumentedEndpoint() {
    const requests = [];
    context.fetch = async (url, options) => {
        requests.push({ url, options });
        return { ok: true, text: async () => JSON.stringify({ detail: 'Successfully logged out.' }) };
    };

    await vm.runInContext('ApiClient.logout()', context);
    assert.equal(requests[0].url, '/api/proxy/rest-auth/logout/');
    assert.equal(requests[0].options.method, 'GET');
}

async function testDeleteModuleUsesModuleEndpoint() {
    const requests = [];
    context.fetch = async (url, options) => {
        requests.push({ url, options });
        return { ok: true, status: 204, text: async () => '' };
    };

    await vm.runInContext('ApiClient.deleteModule(12233)', context);
    assert.equal(requests[0].url, '/api/proxy/api/v1/module/12233');
    assert.equal(requests[0].options.method, 'DELETE');
    assert.equal(requests[0].options.body, undefined);
}

async function testUpdateModulePortUsesDocumentedPayload() {
    const requests = [];
    context.fetch = async (url, options) => {
        requests.push({ url, options });
        return { ok: true, text: async () => JSON.stringify({ id: 13144 }) };
    };
    const payload = {
        version: 975,
        module: 12232,
        default_port: '9011',
        mapping_port: '1111',
    };

    context.modulePortPayload = payload;
    await vm.runInContext('ApiClient.updateModulePort(13144, modulePortPayload)', context);
    assert.equal(requests[0].url, '/api/proxy/api/v1/moduleport/13144');
    assert.equal(requests[0].options.method, 'PUT');
    assert.deepEqual(JSON.parse(requests[0].options.body), payload);
}

(async () => {
    await testGetProjectsPageRequestsOnlyOnePage();
    await testInvalidTokenResponseIsAuthenticationError();
    await testInstallationPackageUsesInstallationResources();
    await testLogoutUsesDocumentedEndpoint();
    await testDeleteModuleUsesModuleEndpoint();
    await testUpdateModulePortUsesDocumentedPayload();
    console.log('PASS: project page requests and invalid Token handling');
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
