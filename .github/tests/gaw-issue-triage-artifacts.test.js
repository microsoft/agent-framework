// Copyright (c) Microsoft. All rights reserved.

const assert = require('node:assert/strict');
const { describe, it } = require('node:test');
const findPreviousTriageArtifact = require('../scripts/gaw-issue-triage-artifacts.js');

function mocks() {
  const calls = [];
  const warnings = [];
  const run = {
    id: 100,
    path: '.github/workflows/gaw-issue-triage.lock.yml',
    repository: { id: 7 },
    head_repository: { id: 7 },
    head_branch: 'main',
    display_title: 'GAW Issue Triage #42',
    event: 'workflow_dispatch',
    status: 'completed',
    conclusion: 'success',
    head_sha: 'a'.repeat(40),
    html_url: 'https://github.com/microsoft/agent-framework/actions/runs/100',
  };
  const artifact = {
    id: 700,
    name: 'gaw-issue-triage-issue-42',
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

describe('Previous issue triage artifacts', () => {
  it('finds an issue-specific bundle and records its actual source run and commit', async () => {
    const input = mocks();
    const result = await findPreviousTriageArtifact(input);
    assert.deepEqual(result, {
      repository: 'microsoft/agent-framework',
      issue_number: 42,
      artifact_name: 'gaw-issue-triage-issue-42',
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

  it('selects only the latest eligible bundle, skipping expired and other-issue artifacts', async () => {
    const input = mocks();
    input.artifacts.push(
      { ...input.artifact, id: 701, created_at: '2026-11-03T11:00:00Z' },
      { ...input.artifact, id: 702, expired: true, created_at: '2026-11-03T12:00:00Z' },
      { ...input.artifact, id: 703, name: 'gaw-issue-triage-issue-420', created_at: '2026-11-03T13:00:00Z' },
    );
    assert.equal((await findPreviousTriageArtifact(input)).artifact_id, 701);
    assert.equal(input.calls.filter(([kind]) => kind === 'run').length, 1);
  });

  it('ignores bundles from other repositories and the current or a later run', async () => {
    for (const workflow_run of [
      undefined,
      { id: 100, repository_id: 8 },
      { id: 1000, repository_id: 7 },
      { id: 1001, repository_id: 7 },
    ]) {
      const input = mocks();
      input.artifact.workflow_run = workflow_run;
      assert.equal(await findPreviousTriageArtifact(input), null);
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
      { display_title: 'GAW Issue Triage #43' },
      { event: 'pull_request' },
      { status: 'in_progress' },
      { conclusion: 'failure' },
      { conclusion: 'cancelled' },
      { head_sha: 'not-a-commit' },
      { head_sha: 'b'.repeat(40) },
    ]) {
      const input = mocks();
      Object.assign(input.run, changes);
      assert.equal(await findPreviousTriageArtifact(input), null, JSON.stringify(changes));
      assert.equal(input.warnings.length, 1);
    }
  });

  it('can fall back to an older bundle when the newest source run is not eligible', async () => {
    const input = mocks();
    input.artifacts.push({
      ...input.artifact, id: 701, created_at: '2026-11-03T11:00:00Z',
      workflow_run: { ...input.artifact.workflow_run, id: 101 },
    });
    input.github.rest.actions.getWorkflowRun = async ({ run_id }) => ({
      data: run_id === 101 ? { ...input.run, id: 101, conclusion: 'failure' } : input.run,
    });
    assert.equal((await findPreviousTriageArtifact(input)).artifact_id, 700);
  });

  it('continues normally when no retained bundle exists', async () => {
    const input = mocks();
    input.artifacts.length = 0;
    assert.equal(await findPreviousTriageArtifact(input), null);
  });

  it('rejects oversized or invalid bundles instead of downloading them', async () => {
    for (const size of [0, -1, 11 * 1024 * 1024 + 1, '100']) {
      const input = mocks();
      input.artifact.size_in_bytes = size;
      await assert.rejects(findPreviousTriageArtifact(input), /download size limit|invalid size/);
    }
  });

  it('validates issue numbers before calling GitHub', async () => {
    for (const issueNumber of ['', '0', '-1', '042', '42\n', '42/../43', '9007199254740992']) {
      const input = { ...mocks(), issueNumber };
      await assert.rejects(findPreviousTriageArtifact(input), /positive, safe integer/);
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
      await assert.rejects(findPreviousTriageArtifact(input), /GitHub access denied/);
    }
  });
});
