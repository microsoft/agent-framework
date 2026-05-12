// Copyright (c) Microsoft. All rights reserved.

/**
 * Tests for check_team_membership.js.
 *
 * Run with: node --test .github/tests/test_check_team_membership.js
 */

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');

const checkTeamMembership = require('../scripts/check_team_membership.js');


// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createMocks({ payloadIssue = undefined, apiUser = 'api-user', teamState = 'active' } = {}) {
  const core = {
    _infoMessages: [],
    _failedMessages: [],
    info(msg) { this._infoMessages.push(msg); },
    setFailed(msg) { this._failedMessages.push(msg); },
  };

  const context = {
    payload: { issue: payloadIssue },
    repo: { owner: 'test-org', repo: 'test-repo' },
  };

  const github = {
    rest: {
      issues: {
        get: async () => ({
          data: { user: apiUser ? { login: apiUser } : null },
        }),
      },
      teams: {
        getByName: async () => ({}),
        getMembershipForUserInOrg: async () => ({
          data: { state: teamState },
        }),
      },
    },
  };

  return { core, context, github };
}

const BASE_OPTS = { teamSlug: 'my-team', issueNumber: '123' };


// ---------------------------------------------------------------------------
// Author resolution
// ---------------------------------------------------------------------------

describe('author resolution', () => {
  it('resolves author from event payload', async () => {
    const { github, context, core } = createMocks({
      payloadIssue: { user: { login: 'payload-user' } },
    });
    const result = await checkTeamMembership({ github, context, core, ...BASE_OPTS });
    assert.equal(result.author, 'payload-user');
  });

  it('resolves author via API when payload issue is absent', async () => {
    const { github, context, core } = createMocks({ apiUser: 'api-user' });
    const result = await checkTeamMembership({ github, context, core, ...BASE_OPTS });
    assert.equal(result.author, 'api-user');
  });

  it('resolves author via API when payload issue user is null (deleted account)', async () => {
    const { github, context, core } = createMocks({
      payloadIssue: { user: null },
      apiUser: 'fetched-user',
    });
    const result = await checkTeamMembership({ github, context, core, ...BASE_OPTS });
    assert.equal(result.author, 'fetched-user');
  });

  it('handles deleted account when API also returns null user', async () => {
    const { github, context, core } = createMocks({ apiUser: null });
    const result = await checkTeamMembership({ github, context, core, ...BASE_OPTS });
    assert.equal(result.author, null);
    assert.equal(result.isTeamMember, false);
    assert.ok(core._failedMessages.some(m => m.includes('deleted')));
  });
});


// ---------------------------------------------------------------------------
// Team lookup
// ---------------------------------------------------------------------------

describe('team lookup', () => {
  it('fails the job when team lookup errors', async () => {
    const { github, context, core } = createMocks({
      payloadIssue: { user: { login: 'user1' } },
    });
    const error = new Error('Bad credentials');
    github.rest.teams.getByName = async () => { throw error; };

    await assert.rejects(
      () => checkTeamMembership({ github, context, core, ...BASE_OPTS }),
      (err) => err === error,
    );
    assert.ok(core._failedMessages.some(m => m.includes('Team lookup failed')));
  });
});


// ---------------------------------------------------------------------------
// Team membership
// ---------------------------------------------------------------------------

describe('team membership', () => {
  it('returns true for active team member', async () => {
    const { github, context, core } = createMocks({
      payloadIssue: { user: { login: 'member' } },
      teamState: 'active',
    });
    const result = await checkTeamMembership({ github, context, core, ...BASE_OPTS });
    assert.equal(result.isTeamMember, true);
  });

  it('returns false for pending team member', async () => {
    const { github, context, core } = createMocks({
      payloadIssue: { user: { login: 'pending-user' } },
      teamState: 'pending',
    });
    const result = await checkTeamMembership({ github, context, core, ...BASE_OPTS });
    assert.equal(result.isTeamMember, false);
  });

  it('treats 404 membership response as non-member without failing', async () => {
    const { github, context, core } = createMocks({
      payloadIssue: { user: { login: 'outsider' } },
    });
    const notFoundError = new Error('Not Found');
    notFoundError.status = 404;
    github.rest.teams.getMembershipForUserInOrg = async () => { throw notFoundError; };

    const result = await checkTeamMembership({ github, context, core, ...BASE_OPTS });
    assert.equal(result.isTeamMember, false);
    assert.equal(core._failedMessages.length, 0);
    assert.ok(core._infoMessages.some(m => m.includes('not a member')));
  });

  it('fails the job on non-404 membership errors', async () => {
    const { github, context, core } = createMocks({
      payloadIssue: { user: { login: 'user1' } },
    });
    const serverError = new Error('Internal Server Error');
    serverError.status = 500;
    github.rest.teams.getMembershipForUserInOrg = async () => { throw serverError; };

    await assert.rejects(
      () => checkTeamMembership({ github, context, core, ...BASE_OPTS }),
      (err) => err === serverError,
    );
    assert.ok(core._failedMessages.some(m => m.includes('membership lookup failed')));
  });

  it('fails the job on membership errors without status code', async () => {
    const { github, context, core } = createMocks({
      payloadIssue: { user: { login: 'user1' } },
    });
    const networkError = new Error('ECONNREFUSED');
    github.rest.teams.getMembershipForUserInOrg = async () => { throw networkError; };

    await assert.rejects(
      () => checkTeamMembership({ github, context, core, ...BASE_OPTS }),
      (err) => err === networkError,
    );
    assert.ok(core._failedMessages.some(m => m.includes('membership lookup failed')));
  });
});
