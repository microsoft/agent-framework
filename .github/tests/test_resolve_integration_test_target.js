// Copyright (c) Microsoft. All rights reserved.

/**
 * Tests for resolve_integration_test_target.js.
 *
 * Run with: node --test .github/tests/test_resolve_integration_test_target.js
 */

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');

const resolveIntegrationTestTarget = require('../scripts/resolve_integration_test_target.js');

const HEAD_SHA = 'a'.repeat(40);
const BASE_SHA = 'b'.repeat(40);

function review({
  id,
  login,
  state = 'APPROVED',
  commitId = HEAD_SHA,
  submittedAt = `2026-07-13T00:00:${String(id).padStart(2, '0')}Z`,
}) {
  return {
    id,
    state,
    commit_id: commitId,
    submitted_at: submittedAt,
    user: { login },
  };
}

function createMocks({
  pullState = 'open',
  pullAuthor = 'contributor',
  reviews = [],
  permissions = {},
} = {}) {
  const core = {
    infoMessages: [],
    info(message) {
      this.infoMessages.push(message);
    },
  };
  const context = {
    repo: { owner: 'microsoft', repo: 'agent-framework' },
  };
  const github = {
    paginate: async () => reviews,
    rest: {
      pulls: {
        get: async () => ({
          data: {
            state: pullState,
            user: { login: pullAuthor },
            head: { sha: HEAD_SHA },
            base: { sha: BASE_SHA },
          },
        }),
        listReviews: async () => {},
      },
      repos: {
        get: async () => ({ data: { default_branch: 'main' } }),
        getBranch: async ({ branch }) => ({
          data: { commit: { sha: branch === 'main' ? BASE_SHA : HEAD_SHA } },
        }),
        getCollaboratorPermissionLevel: async ({ username }) => ({
          data: permissions[username] || {
            permission: 'read',
            user: { permissions: { push: false } },
          },
        }),
      },
    },
  };

  return { core, context, github };
}

const WRITE_PERMISSION = {
  permission: 'write',
  user: { permissions: { push: true } },
};

describe('input validation', () => {
  it('rejects missing and conflicting targets', async () => {
    const mocks = createMocks();
    await assert.rejects(
      () => resolveIntegrationTestTarget(mocks),
      /provide either a PR number or a branch name/,
    );
    await assert.rejects(
      () => resolveIntegrationTestTarget({ ...mocks, prNumber: '1', branch: 'feature' }),
      /not both/,
    );
  });

  it('rejects invalid PR numbers and branch names', async () => {
    const mocks = createMocks();
    await assert.rejects(
      () => resolveIntegrationTestTarget({ ...mocks, prNumber: '1;echo' }),
      /Invalid PR number/,
    );
    await assert.rejects(
      () => resolveIntegrationTestTarget({ ...mocks, branch: 'feature branch' }),
      /Invalid branch name/,
    );
  });
});

describe('pull request resolution', () => {
  it('pins an open PR with two fresh write-capable approvals', async () => {
    const mocks = createMocks({
      reviews: [
        review({ id: 1, login: 'maintainer-one' }),
        review({ id: 2, login: 'maintainer-two' }),
      ],
      permissions: {
        'maintainer-one': WRITE_PERMISSION,
        'maintainer-two': WRITE_PERMISSION,
      },
    });

    const result = await resolveIntegrationTestTarget({ ...mocks, prNumber: '123' });

    assert.deepEqual(result, {
      baseRef: BASE_SHA,
      checkoutRef: HEAD_SHA,
      description: 'PR #123',
    });
  });

  it('rejects closed PRs', async () => {
    const mocks = createMocks({ pullState: 'closed' });
    await assert.rejects(
      () => resolveIntegrationTestTarget({ ...mocks, prNumber: '123' }),
      /is not open/,
    );
  });

  it('ignores stale, self, and read-only approvals', async () => {
    const mocks = createMocks({
      reviews: [
        review({ id: 1, login: 'stale', commitId: 'c'.repeat(40) }),
        review({ id: 2, login: 'contributor' }),
        review({ id: 3, login: 'reader' }),
        review({ id: 4, login: 'maintainer' }),
      ],
      permissions: {
        contributor: WRITE_PERMISSION,
        reader: { permission: 'read', user: { permissions: { push: false } } },
        maintainer: WRITE_PERMISSION,
      },
    });

    await assert.rejects(
      () => resolveIntegrationTestTarget({ ...mocks, prNumber: '123' }),
      /found 1/,
    );
  });

  it('uses each reviewer latest decisive review and ignores later comments', async () => {
    const mocks = createMocks({
      reviews: [
        review({ id: 1, login: 'changes-requested' }),
        review({ id: 2, login: 'changes-requested', state: 'CHANGES_REQUESTED' }),
        review({ id: 3, login: 'maintainer-one' }),
        review({ id: 4, login: 'maintainer-one', state: 'COMMENTED' }),
        review({ id: 5, login: 'maintainer-two' }),
      ],
      permissions: {
        'changes-requested': WRITE_PERMISSION,
        'maintainer-one': WRITE_PERMISSION,
        'maintainer-two': WRITE_PERMISSION,
      },
    });

    const result = await resolveIntegrationTestTarget({ ...mocks, prNumber: '123' });
    assert.equal(result.checkoutRef, HEAD_SHA);
  });

  it('does not count a dismissed approval', async () => {
    const mocks = createMocks({
      reviews: [
        review({ id: 1, login: 'dismissed', state: 'DISMISSED' }),
        review({ id: 2, login: 'maintainer' }),
      ],
      permissions: {
        dismissed: WRITE_PERMISSION,
        maintainer: WRITE_PERMISSION,
      },
    });

    await assert.rejects(
      () => resolveIntegrationTestTarget({ ...mocks, prNumber: '123' }),
      /found 1/,
    );
  });
});

describe('branch resolution', () => {
  it('pins base-repository branches and their comparison base to SHAs', async () => {
    const mocks = createMocks();
    const result = await resolveIntegrationTestTarget({ ...mocks, branch: 'feature/test' });

    assert.deepEqual(result, {
      baseRef: BASE_SHA,
      checkoutRef: HEAD_SHA,
      description: 'branch feature/test',
    });
  });
});
