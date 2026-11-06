// Copyright (c) Microsoft. All rights reserved.

const assert = require('node:assert/strict');
const { describe, it } = require('node:test');
const prepareIssueRouting = require('../scripts/issue-routing-prepare.js');
const { ROUTED_STEP } = require('../scripts/issue-routing-history.js');

// An earlier completed run of this workflow; `routed` controls its publishing step.
function earlierRun(id, { routed = true, event = 'issues', started = '2026-01-02T00:00:00Z' } = {}) {
  return {
    run: { id, event, status: 'completed', display_title: 'Issue Routing #42', run_started_at: started },
    jobs: [{ name: 'safe_outputs', conclusion: 'success', steps: [{ name: ROUTED_STEP, conclusion: routed ? 'success' : 'skipped' }] }],
  };
}

function mocks({ manual = false, event, type = 'Bug', labels = [], member = false, runs = [], commenter = 'author', repliedAt = '2026-01-03T00:00:00Z' } = {}) {
  const outputs = {};
  const calls = [];
  const eventName = event ?? (manual ? 'workflow_dispatch' : 'issues');
  return {
    outputs,
    calls,
    issueNumber: '42',
    teamSlug: 'developers',
    context: {
      eventName,
      runId: 1000,
      repo: { owner: 'microsoft', repo: 'agent-framework' },
      payload: {
        issue: { number: 42, user: { login: 'stale-author' } },
        ...(eventName === 'issue_comment' ? { comment: { user: { login: commenter }, created_at: repliedAt } } : {}),
      },
    },
    actionsGithub: {
      paginate: async (endpoint, params) => endpoint(params),
      rest: {
        actions: {
          listWorkflowRuns: async params => {
            calls.push(['runs', params]);
            return runs.map(entry => entry.run);
          },
          listJobsForWorkflowRun: async ({ run_id }) => runs.find(entry => entry.run.id === run_id).jobs,
        },
      },
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
            return { data: { number: 42, created_at: '2026-01-01T00:00:00Z', type: type ? { name: type } : null, labels, user: { login: 'author' } } };
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

  it('routes new issues and type changes only once, ignoring previews and blocked runs', async () => {
    const fresh = mocks({ runs: [earlierRun(1, { routed: false })] });
    await prepareIssueRouting(fresh);
    assert.equal(fresh.outputs.should_route, 'true');
    assert.equal(fresh.calls.find(([kind]) => kind === 'runs')[1].created, '>=2026-01-01T00:00:00Z');
    const routed = mocks({ runs: [earlierRun(1), earlierRun(1000)] });
    await prepareIssueRouting(routed);
    assert.equal(routed.outputs.should_route, 'false');
    const manual = mocks({ manual: true, runs: [earlierRun(1)] });
    await prepareIssueRouting(manual);
    assert.equal(manual.outputs.should_route, 'true');
    assert.equal(manual.calls.some(([kind]) => kind === 'runs'), false);
  });

  it('re-runs only for a reporter reply on a requested-info issue that no run has seen', async () => {
    const labels = [{ name: 'requested-info' }];
    const reply = mocks({ event: 'issue_comment', labels, runs: [earlierRun(1)] });
    await prepareIssueRouting(reply);
    assert.equal(reply.outputs.should_route, 'true');

    const otherUser = mocks({ event: 'issue_comment', labels, commenter: 'someone-else' });
    await prepareIssueRouting(otherUser);
    assert.equal(otherUser.outputs.should_route, 'false');

    const notRequested = mocks({ event: 'issue_comment' });
    await prepareIssueRouting(notRequested);
    assert.equal(notRequested.outputs.should_route, 'false');

    const alreadySeen = mocks({ event: 'issue_comment', labels, runs: [earlierRun(1, { started: '2026-01-04T00:00:00Z' })] });
    await prepareIssueRouting(alreadySeen);
    assert.equal(alreadySeen.outputs.should_route, 'false');

    const capped = mocks({ event: 'issue_comment', labels, runs: [1, 2, 3].map(id => earlierRun(id, { event: 'issue_comment' })) });
    await prepareIssueRouting(capped);
    assert.equal(capped.outputs.should_route, 'false');
  });
});
