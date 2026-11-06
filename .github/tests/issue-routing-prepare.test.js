// Copyright (c) Microsoft. All rights reserved.

const assert = require('node:assert/strict');
const { describe, it } = require('node:test');
const prepareIssueRouting = require('../scripts/issue-routing-prepare.js');

function mocks({ manual = false, type = 'Bug', labels = [], member = false } = {}) {
  const outputs = {};
  const calls = [];
  return {
    outputs,
    calls,
    issueNumber: '42',
    teamSlug: 'developers',
    context: {
      eventName: manual ? 'workflow_dispatch' : 'issues',
      repo: { owner: 'microsoft', repo: 'agent-framework' },
      payload: { issue: { number: 42, user: { login: 'stale-author' } } },
    },
    core: {
      setOutput: (key, value) => { outputs[key] = value; },
      info() {},
      setFailed: message => { throw new Error(message); },
    },
    github: {
      rest: {
        issues: {
          get: async params => {
            calls.push(['issue', params]);
            return { data: { number: 42, type: type ? { name: type } : null, labels, user: { login: 'author' } } };
          },
        },
        teams: {
          getByName: async () => {},
          getMembershipForUserInOrg: async params => {
            calls.push(['member', params]);
            if (!member) {
              throw Object.assign(new Error('Not Found'), { status: 404 });
            }
            return { data: { state: 'active' } };
          },
        },
      },
    },
  };
}

describe('Issue routing preparation', () => {
  it('uses the fetched issue author, not the event actor or stale payload author', async () => {
    const input = mocks();
    await prepareIssueRouting(input);
    assert.equal(input.outputs.should_route, 'true');
    assert.equal(input.outputs.issue_number, '42');
    assert.equal(input.outputs.issue_type, 'Bug');
    assert.equal(input.calls.find(([kind]) => kind === 'member')[1].username, 'author');
  });

  it('allows automatic Features and skips other or missing native types', async () => {
    for (const type of ['Feature', 'Task', '']) {
      const input = mocks({ type });
      await prepareIssueRouting(input);
      assert.equal(input.outputs.should_route, type === 'Feature' ? 'true' : 'false');
    }
  });

  it('skips team authors automatically but permits manual reruns and arbitrary manual types', async () => {
    const automatic = mocks({ member: true });
    await prepareIssueRouting(automatic);
    assert.equal(automatic.outputs.should_route, 'false');
    const manual = mocks({ member: true, manual: true, type: 'Task' });
    await prepareIssueRouting(manual);
    assert.equal(manual.outputs.should_route, 'true');
    assert.equal(manual.calls.some(([kind]) => kind === 'member'), false);
  });

  it('validates manual issue numbers before making API calls', async () => {
    for (const issueNumber of ['', '0', '-1', '01', '42\n', '42;echo bad', '9007199254740992']) {
      const input = { ...mocks({ manual: true }), issueNumber };
      await assert.rejects(prepareIssueRouting(input), /positive, safe integer/);
      assert.equal(input.calls.length, 0);
      assert.equal(input.outputs.should_route, 'false');
    }
  });

  it('rejects PR numbers and propagates missing-issue errors', async () => {
    const pr = mocks();
    pr.github.rest.issues.get = async () => ({ data: { number: 42, pull_request: {} } });
    await assert.rejects(prepareIssueRouting(pr), /not a pull request/);
    const missing = mocks();
    missing.github.rest.issues.get = async () => { throw new Error('Issue not found'); };
    await assert.rejects(prepareIssueRouting(missing), /Issue not found/);
    assert.equal(missing.outputs.should_route, 'false');
  });

  it('fails closed on missing author, team configuration, and membership lookup errors', async () => {
    const noAuthor = mocks();
    noAuthor.github.rest.issues.get = async () => ({ data: { number: 42, type: { name: 'Bug' } } });
    await assert.rejects(prepareIssueRouting(noAuthor), /current issue author/);
    const noTeam = { ...mocks(), teamSlug: '' };
    await assert.rejects(prepareIssueRouting(noTeam), /developer team/);
    const apiFailure = mocks();
    apiFailure.github.rest.teams.getMembershipForUserInOrg = async () => { throw new Error('API unavailable'); };
    await assert.rejects(prepareIssueRouting(apiFailure), /API unavailable/);
    assert.equal(apiFailure.outputs.should_route, 'false');
  });

  it('keeps deny labels stronger than allow labels, including manual dispatch', async () => {
    for (const manual of [true, false]) {
      for (const label of ['spam', 'suspected-spam', 'needs-maintainer-triage']) {
        const held = mocks({ manual, labels: [{ name: label }] });
        await prepareIssueRouting(held);
        assert.equal(held.outputs.should_route, 'false');
        const released = mocks({ manual, labels: [label.toUpperCase(), 'safe-to-triage'] });
        await prepareIssueRouting(released);
        assert.equal(released.outputs.should_route, label === 'needs-maintainer-triage' ? 'true' : 'false');
      }
    }
  });
});
