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

(async () => {
    await testGetProjectsPageRequestsOnlyOnePage();
    await testInvalidTokenResponseIsAuthenticationError();
    console.log('PASS: project page requests and invalid Token handling');
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
