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
});
