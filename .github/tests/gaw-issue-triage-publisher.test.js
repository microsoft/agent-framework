// Copyright (c) Microsoft. All rights reserved.

const assert = require('node:assert/strict');
const { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join, relative, resolve } = require('node:path');
const { beforeEach, describe, it } = require('node:test');

const runtime = process.env.GH_AW_TEST_RUNTIME;

describe('Issue triage pinned publisher', { skip: runtime ? false : 'Set GH_AW_TEST_RUNTIME to the pinned gh-aw setup scripts; CI runs these tests.' }, () => {
  let main;
  let requests;
  const record = {
    schema_version: 1,
    repository: 'microsoft/agent-framework',
    issue_number: 42,
    commit: 'a'.repeat(40),
    run_url: 'https://github.com/microsoft/agent-framework/actions/runs/123',
    status: 'reproduced',
    kind: 'runtime',
    steps: ['Run the focused local test.'],
    commands: ['python -m pytest tests/test_repro.py -k "local_case"'],
    expected: 'The result includes "quoted text" and a newline.\nNo failure.',
    observed: 'Assertion failed: got an empty result.',
    source_files: ['python/packages/core/agent_framework/_agents.py'],
    test_files: ['artifact:tests/test_repro.py'],
    artifact_name: 'gaw-issue-triage-issue-42',
    documentation: null,
  };

  beforeEach(() => {
    Object.assign(process.env, {
      GITHUB_REPOSITORY: 'microsoft/agent-framework',
      GITHUB_REPOSITORY_ID: '123',
      GITHUB_SERVER_URL: 'https://github.com',
      GITHUB_RUN_ID: '123',
      GITHUB_RUN_ATTEMPT: '1',
      GITHUB_JOB: 'safe_outputs',
      GH_AW_JOB_CHECK_RUN_ID: '456',
      GH_AW_WORKFLOW_ID: 'gaw-issue-triage',
      GH_AW_SAFE_OUTPUTS_STAGED: 'false',
    });
    ({ main } = require(resolve(runtime, 'add_comment.cjs')));
    requests = [];
    global.core = {
      info() {},
      warning() {},
      error() {},
      debug() {},
      setOutput() {},
    };
    global.context = {
      eventName: 'workflow_dispatch',
      payload: {},
      repo: { owner: 'microsoft', repo: 'agent-framework' },
      serverUrl: 'https://github.com',
      runId: 123,
      runNumber: 1,
      workflow: 'GAW Issue Triage',
    };
    global.github = {
      rest: {
        issues: {
          createComment: async request => {
            requests.push(request);
            return { data: { id: 1, html_url: 'https://github.com/microsoft/agent-framework/issues/42#issuecomment-1' } };
          },
        },
      },
    };
  });

  function configuredComment() {
    const compiled = readFileSync(resolve(__dirname, '../workflows/gaw-issue-triage.lock.yml'), 'utf8');
    const value = compiled.match(/GH_AW_SAFE_OUTPUTS_HANDLER_CONFIG: (.+)/)[1];
    const config = JSON.parse(JSON.parse(value)).add_comment;
    assert.equal(config.target, '${{ needs.prepare.outputs.issue_number }}');
    return { ...config, target: '42', mentions: false };
  }

  function comment(kind = 'runtime') {
    const finding = kind === 'runtime'
      ? 'A focused local test reproduced the reported failure.'
      : 'The documentation example disagrees with the supported API.';
    return `${finding}\n\n[Evidence and tests](${record.run_url}).`;
  }

  for (const kind of ['runtime', 'documentation']) {
    it(`publishes a short ${kind} finding and run link without reproduction JSON`, async () => {
      const handler = await main(configuredComment());
      const body = comment(kind);
      const result = await handler({ body, issue_number: 42 });
      assert.equal(result.success, true, result.error);
      assert.equal(requests.length, 1);
      assert.equal(requests[0].issue_number, 42);
      assert.ok(requests[0].body.includes(body.split('\n')[0]));
      assert.ok(requests[0].body.includes(record.run_url));
      assert.doesNotMatch(requests[0].body, /<details>|```json|"schema_version"/);
    });
  }

  it('cannot redirect a manually selected issue or edit an existing comment', async () => {
    for (const message of [{ issue_number: 999 }, { item_number: 999 }]) {
      const handler = await main(configuredComment());
      const result = await handler({ body: comment(), ...message });
      assert.equal(result.success, true, result.error);
    }
    assert.ok(requests.every(request => request.issue_number === 42 && request.owner === 'microsoft' && request.repo === 'agent-framework'));
    const count = requests.length;
    for (const message of [{ comment_id: 999 }, { repo: 'other/repository' }]) {
      const handler = await main(configuredComment());
      const result = await handler({ body: comment(), ...message });
      assert.equal(result.success, false, JSON.stringify(message));
    }
    assert.equal(requests.length, count);
  });

  it('previews without publishing and limits a real run to one comment', async () => {
    const preview = await main({ ...configuredComment(), staged: true });
    const result = await preview({ body: comment() });
    assert.equal(result.success, true, result.error);
    assert.equal(result.staged, true);
    assert.equal(requests.length, 0);
    const handler = await main(configuredComment());
    assert.equal((await handler({ body: comment() })).success, true);
    assert.equal((await handler({ body: comment() })).success, false);
    assert.equal(requests.length, 1);
  });

  async function checkArtifactUpload(confirmed) {
    const directory = mkdtempSync(join(tmpdir(), 'gaw-triage-upload-'));
    const savedTemp = process.env.RUNNER_TEMP;
    const savedResolver = process.env.GH_AW_ARTIFACT_RESOLVER_FILE;
    process.env.RUNNER_TEMP = directory;
    process.env.GH_AW_ARTIFACT_RESOLVER_FILE = join(directory, 'resolver.json');
    const uploads = [];
    global.__createArtifactClient = () => ({
      uploadArtifact: async (...args) => {
        uploads.push(args);
        return { id: 700, size: 20 };
      },
    });
    try {
      const staging = join(directory, 'gh-aw', 'safeoutputs', 'upload-artifacts');
      for (const issue of ['42', '43']) {
        mkdirSync(join(staging, `gaw-issue-triage-issue-${issue}`), { recursive: true });
        writeFileSync(join(staging, `gaw-issue-triage-issue-${issue}`, 'report.txt'), 'Observed failure.');
      }
      const bundle = join(staging, 'gaw-issue-triage-issue-42');
      const historical = { ...record, run_url: record.run_url.replace('/123', '/100'), commit: 'b'.repeat(40) };
      mkdirSync(join(bundle, 'history', '100'), { recursive: true });
      writeFileSync(join(bundle, 'history', '100', 'reproduction.json'), JSON.stringify(historical, null, 2));
      writeFileSync(join(bundle, 'report.txt'), confirmed
        ? 'Current run: reproduced. Retained earlier evidence from run 100.'
        : 'Current run: inconclusive. Retained earlier evidence from run 100; no new reproduction.');
      if (confirmed) writeFileSync(join(bundle, 'reproduction.json'), JSON.stringify(record, null, 2));
      const compiled = readFileSync(resolve(__dirname, '../workflows/gaw-issue-triage.lock.yml'), 'utf8');
      const config = JSON.parse(JSON.parse(compiled.match(/GH_AW_SAFE_OUTPUTS_HANDLER_CONFIG: (.+)/)[1])).upload_artifact;
      const uploadModule = require.resolve(resolve(runtime, 'upload_artifact.cjs'));
      delete require.cache[uploadModule];
      const { main: upload } = require(uploadModule);
      const handler = await upload({
        ...config,
        'allowed-paths': config['allowed-paths'].map(pattern => pattern.replace('${{ needs.prepare.outputs.issue_number }}', '42')),
        'retention-days': 7,
      });
      assert.equal((await handler({ path: 'gaw-issue-triage-issue-43' })).success, false);
      assert.equal(uploads.length, 0);
      const result = await handler({ path: 'gaw-issue-triage-issue-42' });
      assert.equal(result.success, true, result.error);
      assert.equal(uploads.length, 1);
      assert.equal(result.artifactName, 'gaw-issue-triage-issue-42');
      assert.equal(uploads[0][0], 'gaw-issue-triage-issue-42');
      const expected = ['report.txt', join('history', '100', 'reproduction.json')];
      if (confirmed) expected.push('reproduction.json');
      assert.deepEqual(uploads[0][1].map(file => relative(bundle, file)).sort(), expected.sort());
      assert.deepEqual(JSON.parse(readFileSync(join(bundle, 'history', '100', 'reproduction.json'), 'utf8')), historical);
      if (confirmed) assert.deepEqual(JSON.parse(readFileSync(join(bundle, 'reproduction.json'), 'utf8')), record);
      assert.equal(resolve(uploads[0][2]), staging);
      assert.equal(uploads[0][3].retentionDays, 7);
    } finally {
      if (savedTemp === undefined) delete process.env.RUNNER_TEMP;
      else process.env.RUNNER_TEMP = savedTemp;
      if (savedResolver === undefined) delete process.env.GH_AW_ARTIFACT_RESOLVER_FILE;
      else process.env.GH_AW_ARTIFACT_RESOLVER_FILE = savedResolver;
      delete global.__createArtifactClient;
      rmSync(directory, { recursive: true, force: true });
    }
  }

  for (const confirmed of [true, false]) {
    it(`uploads a ${confirmed ? 'newly reproduced' : 'retained-only'} bundle with its original historical record`,
      () => checkArtifactUpload(confirmed));
  }
});
