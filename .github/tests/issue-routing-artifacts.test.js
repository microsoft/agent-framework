// Copyright (c) Microsoft. All rights reserved.

const assert = require('node:assert/strict');
const { describe, it } = require('node:test');
const {
  findEarlierEvidence,
  findThisRunsEvidence,
} = require('../scripts/issue-routing-artifacts.js');

function mocks() {
  const calls = [];
  const warnings = [];
  const run = {
    id: 100,
    path: '.github/workflows/issue-routing.lock.yml',
    repository: { id: 7 },
    head_repository: { id: 7 },
    head_branch: 'main',
    display_title: 'Issue Routing #42',
    event: 'workflow_dispatch',
    status: 'completed',
    conclusion: 'success',
    head_sha: 'a'.repeat(40),
    html_url: 'https://github.com/microsoft/agent-framework/actions/runs/100',
  };
  const artifact = {
    id: 700,
    name: 'issue-routing-issue-42',
    expired: false,
    created_at: '2026-11-03T10:00:00Z',
    size_in_bytes: 100,
    workflow_run: { id: 100, repository_id: 7, head_sha: run.head_sha },
  };
  const artifacts = [artifact];
  return {
    calls, warnings, run, artifact, artifacts,
    issueNumber: '42',
    context: { repo: { owner: 'microsoft', repo: 'agent-framework' }, runId: 1000 },
    core: { info() {}, warning: message => warnings.push(message) },
    github: {
      rest: {
        repos: { get: async () => ({ data: { id: 7, default_branch: 'main' } }) },
        actions: {
          listArtifactsForRepo() {},
          getWorkflowRun: async params => {
            calls.push(['run', params]);
            return { data: run };
          },
        },
      },
      paginate: async (method, params) => {
        calls.push(['list', params]);
        return artifacts;
      },
    },
  };
}

describe('Previous issue routing artifacts', () => {
  it('finds evidence saved for this issue and records its actual source run and commit', async () => {
    const input = mocks();
    const result = await findEarlierEvidence(input);
    assert.deepEqual(result, {
      repository: 'microsoft/agent-framework',
      issue_number: 42,
      artifact_name: 'issue-routing-issue-42',
      artifact_id: 700,
      run_id: 100,
      run_url: input.run.html_url,
      run_commit: input.run.head_sha,
      created_at: input.artifact.created_at,
    });
    assert.deepEqual(input.calls, [
      ['list', { owner: 'microsoft', repo: 'agent-framework', name: result.artifact_name, per_page: 100 }],
      ['run', { owner: 'microsoft', repo: 'agent-framework', run_id: 100 }],
    ]);
  });

  it('selects only the latest eligible evidence, skipping expired and other-issue uploads', async () => {
    const input = mocks();
    input.artifacts.push(
      { ...input.artifact, id: 701, created_at: '2026-11-03T11:00:00Z' },
      { ...input.artifact, id: 702, expired: true, created_at: '2026-11-03T12:00:00Z' },
      { ...input.artifact, id: 703, name: 'issue-routing-issue-420', created_at: '2026-11-03T13:00:00Z' },
    );
    assert.equal((await findEarlierEvidence(input)).artifact_id, 701);
    assert.equal(input.calls.filter(([kind]) => kind === 'run').length, 1);
  });

  it('ignores evidence from other repositories and the current or a later run', async () => {
    for (const workflow_run of [
      undefined,
      { id: 100, repository_id: 8 },
      { id: 1000, repository_id: 7 },
      { id: 1001, repository_id: 7 },
    ]) {
      const input = mocks();
      input.artifact.workflow_run = workflow_run;
      assert.equal(await findEarlierEvidence(input), null);
      assert.equal(input.calls.some(([kind]) => kind === 'run'), false);
    }
  });

  it('rejects matching names without the expected workflow, issue, branch, revision, and successful result', async () => {
    for (const changes of [
      { path: '.github/workflows/unrelated.yml' },
      { repository: { id: 8 } },
      { head_repository: { id: 8 } },
      { head_repository: null },
      { head_branch: 'untrusted-branch' },
      { display_title: 'Issue Routing #43' },
      { event: 'pull_request' },
      { status: 'in_progress' },
      { conclusion: 'failure' },
      { conclusion: 'cancelled' },
      { head_sha: 'not-a-commit' },
      { head_sha: 'b'.repeat(40) },
    ]) {
      const input = mocks();
      Object.assign(input.run, changes);
      assert.equal(await findEarlierEvidence(input), null, JSON.stringify(changes));
      assert.equal(input.warnings.length, 1);
    }
  });

  it('can fall back to an older upload when the newest source run is not eligible', async () => {
    const input = mocks();
    input.artifacts.push({
      ...input.artifact, id: 701, created_at: '2026-11-03T11:00:00Z',
      workflow_run: { ...input.artifact.workflow_run, id: 101 },
    });
    input.github.rest.actions.getWorkflowRun = async ({ run_id }) => ({
      data: run_id === 101 ? { ...input.run, id: 101, conclusion: 'failure' } : input.run,
    });
    assert.equal((await findEarlierEvidence(input)).artifact_id, 700);
  });

  it('continues normally when no saved evidence exists', async () => {
    const input = mocks();
    input.artifacts.length = 0;
    assert.equal(await findEarlierEvidence(input), null);
  });

  it('rejects invalid upload details instead of downloading it', async () => {
    for (const size of [0, -1, '100']) {
      const input = mocks();
      input.artifact.size_in_bytes = size;
      await assert.rejects(findEarlierEvidence(input), /download size limit|invalid size/);
    }
  });

  it('skips an oversized upload and falls back to older evidence or none', async () => {
    const input = mocks();
    input.artifacts.push({
      ...input.artifact, id: 701, created_at: '2026-11-03T11:00:00Z',
      size_in_bytes: 11 * 1024 * 1024 + 1,
    });
    assert.equal((await findEarlierEvidence(input)).artifact_id, 700);
    assert.match(input.warnings[0], /exceeds the 11 MiB/);
    input.artifact.size_in_bytes = 12 * 1024 * 1024;
    assert.equal(await findEarlierEvidence(input), null);
  });

  it('finds only this run\'s temporary copy and rejects oversized uploads and API errors', async () => {
    const input = mocks();
    input.github.rest.actions.listWorkflowRunArtifacts = () => {};
    input.github.paginate = async (method, params) => {
      assert.equal(method, input.github.rest.actions.listWorkflowRunArtifacts);
      assert.equal(params.run_id, 1000);
      return input.artifacts;
    };
    assert.equal(await findThisRunsEvidence(input), null);
    input.artifact.name = 'issue-routing-transfer';
    assert.equal(await findThisRunsEvidence(input), 700);
    input.artifact.expired = true;
    assert.equal(await findThisRunsEvidence(input), null);
    input.artifact.expired = false;
    for (const size of [0, -1, '100']) {
      input.artifact.size_in_bytes = size;
      await assert.rejects(findThisRunsEvidence(input), /invalid size/);
    }
    input.artifact.size_in_bytes = 14 * 1024 * 1024 + 1;
    await assert.rejects(findThisRunsEvidence(input), /too large/);
    input.github.paginate = async () => { throw new Error('Access denied'); };
    await assert.rejects(findThisRunsEvidence(input), /Access denied/);
  });

  it('validates issue numbers before calling GitHub', async () => {
    for (const issueNumber of ['', '0', '-1', '042', '42\n', '42/../43', '9007199254740992']) {
      const input = { ...mocks(), issueNumber };
      await assert.rejects(findEarlierEvidence(input), /positive, safe integer/);
      assert.equal(input.calls.length, 0);
    }
  });

  it('requires the current run for the temporary copy instead of falling back to repository-wide lookup', async () => {
    for (const runId of [undefined, 0, '1000']) {
      const input = mocks();
      input.context.runId = runId;
      await assert.rejects(findThisRunsEvidence(input), /current workflow run ID/);
      assert.equal(input.calls.length, 0);
    }
  });

  it('does not hide repository, artifact-list, or source-run API errors', async () => {
    for (const endpoint of ['repository', 'list', 'run']) {
      const input = mocks();
      const fail = async () => { throw new Error('GitHub access denied'); };
      if (endpoint === 'repository') input.github.rest.repos.get = fail;
      if (endpoint === 'list') input.github.paginate = fail;
      if (endpoint === 'run') input.github.rest.actions.getWorkflowRun = fail;
      await assert.rejects(findEarlierEvidence(input), /GitHub access denied/);
    }
  });
});
