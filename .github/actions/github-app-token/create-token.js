// Copyright (c) Microsoft. All rights reserved.

const crypto = require('node:crypto');
const { appendFileSync } = require('node:fs');
const { execFileSync } = require('node:child_process');

function base64Url(value) {
  return Buffer.from(value).toString('base64url');
}

function base64ToBase64Url(value) {
  return Buffer.from(value, 'base64').toString('base64url');
}

function createJwtSigningInput(clientId, nowSeconds) {
  const header = base64Url(JSON.stringify({ alg: 'RS256', typ: 'JWT' }));
  const payload = base64Url(JSON.stringify({
    iat: nowSeconds - 60,
    exp: nowSeconds + 540,
    iss: clientId,
  }));
  return `${header}.${payload}`;
}

function signJwt(signingInput, config, execute = execFileSync) {
  const digest = crypto.createHash('sha256').update(signingInput).digest('base64');
  const signature = execute(
    'az',
    [
      'keyvault', 'key', 'sign',
      '--subscription', config.azureSubscriptionId,
      '--vault-name', config.keyVaultName,
      '--name', config.keyName,
      '--algorithm', 'RS256',
      '--digest', digest,
      '--query', 'signature',
      '--output', 'tsv',
      '--only-show-errors',
    ],
    { encoding: 'utf8' },
  ).trim();

  if (!signature) {
    throw new Error('Key Vault returned an empty signature.');
  }

  return `${signingInput}.${base64ToBase64Url(signature)}`;
}

function requestedPermissions(config) {
  const contents = config.contentsPermission ?? 'read';
  const actions = config.actionsPermission ?? 'none';
  const issues = config.issuesPermission ?? 'write';
  const pullRequests = config.pullRequestsPermission ?? 'write';
  if (!['read', 'write'].includes(contents) || !['none', 'read'].includes(actions) ||
      !['read', 'write'].includes(issues) || !['read', 'write'].includes(pullRequests)) {
    throw new Error('Invalid requested GitHub App permissions.');
  }
  return {
    contents,
    issues,
    members: 'read',
    pull_requests: pullRequests,
    ...(actions === 'read' ? { actions: 'read' } : {}),
  };
}

function authorizationMetadata(result) {
  if (!result.permissions || typeof result.permissions !== 'object' || Array.isArray(result.permissions) ||
      !Array.isArray(result.repositories) || result.repositories.length === 0 ||
      result.repositories.some((repo) => !Number.isSafeInteger(repo.id) || repo.id <= 0 ||
        typeof repo.full_name !== 'string' || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo.full_name))) {
    return {};
  }
  const permissions = {};
  for (const [name, value] of Object.entries(result.permissions)) {
    if (/^[a-z_]+$/.test(name) && ['read', 'write', 'admin'].includes(value)) permissions[name] = value;
  }
  return {
    permissions,
    repositories: result.repositories.map(({ id, full_name }) => ({ id, full_name })),
  };
}

async function createInstallationToken(config, dependencies = {}) {
  const permissions = requestedPermissions(config);
  const execute = dependencies.execute ?? execFileSync;
  const request = dependencies.fetch ?? fetch;
  const nowSeconds = dependencies.nowSeconds ?? Math.floor(Date.now() / 1000);
  const repositoryParts = config.targetRepository.split('/');

  if (repositoryParts.length !== 2 || repositoryParts.some((part) => part.length === 0)) {
    throw new Error('TARGET_REPOSITORY must use the owner/repository format.');
  }

  const [, repository] = repositoryParts;
  const signingInput = createJwtSigningInput(config.githubAppClientId, nowSeconds);
  const jwt = signJwt(signingInput, config, execute);

  const response = await request(
    `https://api.github.com/app/installations/${config.githubAppInstallationId}/access_tokens`,
    {
      method: 'POST',
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: `Bearer ${jwt}`,
        'X-GitHub-Api-Version': '2022-11-28',
      },
      body: JSON.stringify({
        repositories: [repository],
        permissions,
      }),
    },
  );

  if (!response.ok) {
    throw new Error(`GitHub installation token request failed with HTTP ${response.status}.`);
  }

  const result = await response.json();
  if (typeof result.token !== 'string' || result.token.length === 0) {
    throw new Error('GitHub returned an empty installation token.');
  }

  const authorization = authorizationMetadata(result);
  if ((config.contentsPermission === 'write' || config.actionsPermission === 'read' ||
       config.issuesPermission === 'read' || config.pullRequestsPermission === 'read') &&
      (authorization.repositories?.length !== 1 ||
       authorization.repositories[0].full_name !== config.targetRepository ||
       authorization.permissions?.contents !== permissions.contents ||
       (permissions.actions && authorization.permissions?.actions !== permissions.actions) ||
       authorization.permissions?.issues !== permissions.issues ||
       authorization.permissions?.pull_requests !== permissions.pull_requests)) {
    throw new Error('GitHub did not confirm requested repository permissions.');
  }
  dependencies.onAuthorization?.(authorization);

  return result.token;
}

function readConfig(environment) {
  const config = {
    azureSubscriptionId: environment.AZURE_SUBSCRIPTION_ID,
    keyVaultName: environment.KEY_VAULT_NAME,
    keyName: environment.KEY_NAME,
    githubAppClientId: environment.GITHUB_APP_CLIENT_ID,
    githubAppInstallationId: environment.GITHUB_APP_INSTALLATION_ID,
    targetRepository: environment.TARGET_REPOSITORY,
  };

  if (Object.values(config).some((value) => !value)) {
    throw new Error('Required GitHub App authentication configuration is missing.');
  }

  config.contentsPermission = environment.CONTENTS_PERMISSION || 'read';
  config.actionsPermission = environment.ACTIONS_PERMISSION || 'none';
  config.issuesPermission = environment.ISSUES_PERMISSION || 'write';
  config.pullRequestsPermission = environment.PULL_REQUESTS_PERMISSION || 'write';
  requestedPermissions(config);

  return config;
}

async function main() {
  try {
    const token = await createInstallationToken(readConfig(process.env), {
      onAuthorization: (authorization) => {
        if (process.env.GITHUB_OUTPUT) {
          appendFileSync(process.env.GITHUB_OUTPUT, `authorization=${JSON.stringify(authorization)}\n`);
        }
      },
    });
    process.stdout.write(token);
  } catch {
    console.error('GitHub App token generation failed.');
    process.exitCode = 1;
  }
}

if (require.main === module) {
  void main();
}

module.exports = {
  authorizationMetadata,
  requestedPermissions,
  base64ToBase64Url,
  createInstallationToken,
  createJwtSigningInput,
  readConfig,
  signJwt,
};
