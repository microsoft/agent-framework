// Copyright (c) Microsoft. All rights reserved.

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const { findRoutedRuns, automaticSkipReason, ROUTED_STEP } = require('../scripts/issue-routing-history.js');

const issue = { number: 42, created_at: '2026-01-01T00:00:00Z' };

function run(id, overrides = {}) {
  return {
    id,
    event: 'issues',
    status: 'completed',
    display_title: 'Issue Routing #42',
    run_started_at: `2026-01-0${id}T00:00:00Z`,
    ...overrides,
  };
}

function published({ job = 'success', step = 'success' } = {}) {
  return [{ name: 'safe_outputs', conclusion: job, steps: [{ name: ROUTED_STEP, conclusion: step }] }];
}

function mocks(runs, jobsById, { eventName = 'issues', comment } = {}) {
  const jobCalls = [];
  return {
    jobCalls,
    context: {
      eventName,
      runId: 9,
      repo: { owner: 'microsoft', repo: 'agent-framework' },
      payload: comment ? { comment } : {},
    },
    github: {
      paginate: async (endpoint, params) => endpoint(params),
      rest: {
        actions: {
          listWorkflowRuns: async () => runs,
          listJobsForWorkflowRun: async ({ run_id }) => {
            jobCalls.push(run_id);
            return jobsById[run_id] ?? [];
          },
        },
      },
    },
  };
}

describe('Issue routing history', () => {
  it('counts only finished runs for this issue that really published, oldest first', async () => {
    const runs = [
      run(5),
      run(1),
      run(2, { display_title: 'Issue Routing #420' }),
      run(3, { status: 'in_progress' }),
      run(4),
      run(6),
      run(9),
    ];
    const jobs = {
      1: published(),
      4: published({ step: 'skipped' }), // preview or blocked by policy
      5: published(),
      6: published({ job: 'failure' }),
      9: published(),
    };
    const input = mocks(runs, jobs);
    const routed = await findRoutedRuns({ ...input, issue });
    assert.deepEqual(routed.map(entry => entry.id), [1, 5]);
    assert.deepEqual(input.jobCalls, [1, 4, 5, 6]);
  });

  it('requires the reply time for comment events', async () => {
    const input = mocks([], {}, { eventName: 'issue_comment', comment: {} });
    await assert.rejects(automaticSkipReason({ ...input, issue }), /no creation time/);
  });

  it('skips a reply that a routed run already started after, and allows a newer reply', async () => {
    const runs = [run(1), run(3, { event: 'issue_comment' })];
    const jobs = { 1: published(), 3: published() };
    const seen = mocks(runs, jobs, { eventName: 'issue_comment', comment: { created_at: '2026-01-02T00:00:00Z' } });
    assert.match(await automaticSkipReason({ ...seen, issue }), /already included this reply/);
    const newer = mocks(runs, jobs, { eventName: 'issue_comment', comment: { created_at: '2026-01-04T00:00:00Z' } });
    assert.equal(await automaticSkipReason({ ...newer, issue }), '');
  });
});
