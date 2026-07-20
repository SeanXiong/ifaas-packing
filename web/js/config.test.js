const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const files = {
    favorites: {
        accounts: {
            alice: { project_ids: ['101'] },
            bob: { project_ids: ['202'] },
        },
    },
    'login-profiles': {
        accounts: {
            alice: { username: 'alice', password: 'local-password' },
        },
    },
};

const context = {
    fetch: async (url, options = {}) => {
        const name = url.split('/').pop();
        if (options.method === 'POST') {
            files[name] = JSON.parse(options.body);
            return { ok: true, json: async () => ({ ok: true }) };
        }
        if (!files[name]) return { ok: false, status: 404 };
        return { ok: true, json: async () => files[name] };
    },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(__dirname + '/config.js', 'utf8'), context);

(async () => {
    const alice = await vm.runInContext("ConfigStore.loadFavorites('alice')", context);
    const bob = await vm.runInContext("ConfigStore.loadFavorites('bob')", context);
    assert.deepEqual(Array.from(alice), ['101']);
    assert.deepEqual(Array.from(bob), ['202']);

    await vm.runInContext("ConfigStore.saveFavoriteProjects('alice', [{ id: 101, name: 'Alice Project' }])", context);
    const cachedProjects = await vm.runInContext("ConfigStore.loadFavoriteProjects('alice')", context);
    assert.deepEqual(JSON.parse(JSON.stringify(cachedProjects)), [{ id: 101, name: 'Alice Project' }]);
    assert.equal(files.favorites.accounts.alice.project_ids, undefined);

    await vm.runInContext("ConfigStore.toggleFavorite('alice', '303')", context);
    const bobAfterAliceChange = await vm.runInContext("ConfigStore.loadFavorites('bob')", context);
    assert.deepEqual(Array.from(bobAfterAliceChange), ['202']);
    assert.deepEqual(files.favorites.accounts.alice.project_ids, ['101', '303']);
    const profile = await vm.runInContext("ConfigStore.loadLoginProfile('alice')", context);
    assert.deepEqual(JSON.parse(JSON.stringify(profile)), { username: 'alice', password: 'local-password' });
    const missingProfile = await vm.runInContext("ConfigStore.loadLoginProfile('missing')", context);
    assert.equal(missingProfile, null);
    await vm.runInContext("ConfigStore.saveLoginProfile('alice', 'new-password')", context);
    await vm.runInContext("ConfigStore.saveLoginProfile('bob', 'bob-password')", context);
    assert.deepEqual(files['login-profiles'].accounts.alice, { username: 'alice', password: 'new-password' });
    assert.deepEqual(files['login-profiles'].accounts.bob, { username: 'bob', password: 'bob-password' });
    console.log('PASS: favorites are isolated by login account');
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
