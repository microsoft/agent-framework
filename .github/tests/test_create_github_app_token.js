// Copyright (c) Microsoft. All rights reserved.

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');

const {
  base64ToBase64Url,
  createInstallationToken,
  createJwtSigningInput,
  readConfig,
} = require('../actions/github-app-token/create-token.js');

const CONFIG = {
  azureSubscriptionId: 'subscription-id',
  keyVaultName: 'vault-name',
  keyName: 'key-name',
  githubAppClientId: 'client-id',
  githubAppInstallationId: '12345',
  targetRepository: 'microsoft/agent-framework',
};

describe('GitHub App token creation', () => {
  it('creates a short-lived GitHub App JWT', () => {
    const signingInput = createJwtSigningInput('client-id', 1_000);
    const [encodedHeader, encodedPayload] = signingInput.split('.');
    const header = JSON.parse(Buffer.from(encodedHeader, 'base64url').toString());
    const payload = JSON.parse(Buffer.from(encodedPayload, 'base64url').toString());

    assert.deepEqual(header, { alg: 'RS256', typ: 'JWT' });
    assert.deepEqual(payload, { iat: 940, exp: 1_540, iss: 'client-id' });
  });

  it('converts Key Vault signatures to unpadded base64url', () => {
    assert.equal(base64ToBase64Url('+/8='), '-_8');
  });

  it('requests a repository-scoped installation token', async () => {
    let request;
    const token = await createInstallationToken(CONFIG, {
      nowSeconds: 1_000,
      execute: (command, args) => {
        assert.equal(command, 'az');
        assert.ok(args.includes('RS256'));
        return '+/8=\n';
      },
      fetch: async (url, options) => {
        request = { url, options };
        return {
          ok: true,
          json: async () => ({ token: 'installation-token' }),
        };
      },
    });

    assert.equal(token, 'installation-token');
    assert.equal(request.url, 'https://api.github.com/app/installations/12345/access_tokens');
    assert.match(request.options.headers.Authorization, /^Bearer [^.]+\.[^.]+\.-_8$/);
    assert.deepEqual(JSON.parse(request.options.body), {
      repositories: ['agent-framework'],
      permissions: {
        contents: 'read',
        issues: 'write',
        members: 'read',
        pull_requests: 'write',
      },
    });
  });

  it('rejects incomplete configuration', () => {
    assert.throws(
      () => readConfig({}),
      /Required GitHub App authentication configuration is missing/,
    );
  });

  it('rejects repository values with extra path segments before signing', async () => {
    let signed = false;

    await assert.rejects(
      createInstallationToken(
        { ...CONFIG, targetRepository: 'microsoft/agent-framework/extra' },
        {
          execute: () => {
            signed = true;
            return '+/8=\n';
          },
        },
      ),
      /TARGET_REPOSITORY must use the owner\/repository format/,
    );
    assert.equal(signed, false);
  });

  it('rejects an empty Key Vault signature', async () => {
    await assert.rejects(
      createInstallationToken(CONFIG, {
        execute: () => '\n',
      }),
      /Key Vault returned an empty signature/,
    );
  });

  it('rejects a failed GitHub token request', async () => {
    await assert.rejects(
      createInstallationToken(CONFIG, {
        execute: () => '+/8=\n',
        fetch: async () => ({ ok: false, status: 403 }),
      }),
      /GitHub installation token request failed with HTTP 403/,
    );
  });

  it('rejects an empty GitHub installation token', async () => {
    await assert.rejects(
      createInstallationToken(CONFIG, {
        execute: () => '+/8=\n',
        fetch: async () => ({
          ok: true,
          json: async () => ({ token: '' }),
        }),
      }),
      /GitHub returned an empty installation token/,
    );
  });
});

describe('opt-in publishing permissions', () => {
  const { authorizationMetadata, requestedPermissions } = require('../actions/github-app-token/create-token.js');
  const authorization = {
    permissions: { contents: 'write', actions: 'read', issues: 'write', pull_requests: 'write' },
    repositories: [{ id: 123, full_name: CONFIG.targetRepository }],
  };

  it('requests write/actions only when explicitly opted in and emits actual grants', async () => {
    let emitted;
    const token = await createInstallationToken({ ...CONFIG, contentsPermission: 'write', actionsPermission: 'read' }, {
      execute: () => '+/8=\n',
      fetch: async (_url, options) => {
        const request = JSON.parse(options.body);
        assert.equal(request.permissions.contents, 'write');
        assert.equal(request.permissions.actions, 'read');
        return { ok: true, json: async () => ({ token: 'secret-token', ...authorization }) };
      },
      onAuthorization: (value) => { emitted = value; },
    });
    assert.equal(token, 'secret-token');
    assert.deepEqual(emitted, authorization);
    assert.ok(!JSON.stringify(emitted).includes('secret-token'));
  });

  it('rejects invalid permission input before signing', async () => {
    for (const invalid of [{ contentsPermission: 'admin' }, { actionsPermission: 'write' }]) {
      let signed = false;
      await assert.rejects(createInstallationToken({ ...CONFIG, ...invalid }, {
        execute: () => { signed = true; return '+/8=\n'; },
      }), /Invalid requested GitHub App permissions/);
      assert.equal(signed, false);
    }
  });

  it('fails publishing token creation when GitHub does not confirm actual grants', async () => {
    for (const grants of [{}, { ...authorization, permissions: { contents: 'read', actions: 'read' } },
      { ...authorization, repositories: [{ id: 456, full_name: 'other/repo' }] },
      { ...authorization, repositories: [...authorization.repositories, { id: 456, full_name: 'other/repo' }] }]) {
      await assert.rejects(createInstallationToken({ ...CONFIG, contentsPermission: 'write', actionsPermission: 'read' }, {
        execute: () => '+/8=\n',
        fetch: async () => ({ ok: true, json: async () => ({ token: 'secret', ...grants }) }),
      }), /GitHub did not confirm requested repository permissions/);
    }
  });

  it('keeps authorization metadata bounded to actual repository identities and permissions', () => {
    const result = authorizationMetadata({
      token: 'secret', permissions: { contents: 'write', actions: 'read', invalid: 'token-secret' },
      repositories: [{ id: 123, full_name: 'owner/repo', temp_clone_token: 'secret' }],
    });
    assert.deepEqual(result, {
      permissions: { contents: 'write', actions: 'read' },
      repositories: [{ id: 123, full_name: 'owner/repo' }],
    });
    assert.deepEqual(authorizationMetadata({ token: 'secret' }), {});
    assert.deepEqual(authorizationMetadata({ permissions: {}, repositories: [{ id: 1, full_name: 'owner/repo\noutput=bad' }] }), {});
  });

  it('keeps existing default grants unchanged', () => {
    assert.equal(requestedPermissions(CONFIG).contents, 'read');
    assert.ok(!Object.hasOwn(requestedPermissions(CONFIG), 'actions'));
  });
});

describe('read-only repair controller permissions', () => {
  const config = { ...CONFIG, contentsPermission: 'read', actionsPermission: 'read',
    issuesPermission: 'read', pullRequestsPermission: 'read' };
  const grants = { contents: 'read', actions: 'read', issues: 'read', pull_requests: 'read' };

  it('requests and verifies read-only repository grants', async () => {
    const token = await createInstallationToken(config, {
      execute: () => '+/8=\n',
      fetch: async (_url, options) => {
        assert.deepEqual(JSON.parse(options.body).permissions, { ...grants, members: 'read' });
        return { ok: true, json: async () => ({ token: 'read-token', permissions: grants,
          repositories: [{ id: 123, full_name: CONFIG.targetRepository }] }) };
      },
    });
    assert.equal(token, 'read-token');
  });

  it('rejects unexpectedly writable or missing read grants', async () => {
    for (const key of ['contents', 'issues', 'pull_requests', 'actions']) {
      await assert.rejects(createInstallationToken(config, {
        execute: () => '+/8=\n',
        fetch: async () => ({ ok: true, json: async () => ({ token: 'wrong-token',
          permissions: { ...grants, [key]: 'write' }, repositories: [{ id: 123, full_name: CONFIG.targetRepository }] }) }),
      }), /did not confirm/);
    }
  });

  it('rejects invalid issue/pull-request permissions before signing', async () => {
    for (const invalid of [{ issuesPermission: 'admin' }, { pullRequestsPermission: 'none' }]) {
      let signed = false;
      await assert.rejects(createInstallationToken({ ...config, ...invalid }, {
        execute: () => { signed = true; return '+/8=\n'; },
      }), /Invalid requested/);
      assert.equal(signed, false);
    }
  });
});
