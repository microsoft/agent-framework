// Copyright (c) Microsoft. All rights reserved.

const assert = require('node:assert/strict');
const { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join, resolve } = require('node:path');
const { beforeEach, describe, it } = require('node:test');
const checkEvidenceFiles = require('../scripts/issue-routing-evidence.js');
const { validateRequests } = require('../scripts/issue-routing-publish.js');

const runtime = process.env.GH_AW_TEST_RUNTIME;

describe('Issue routing pinned publisher', { skip: runtime ? false : 'Set GH_AW_TEST_RUNTIME to the pinned gh-aw setup scripts; CI runs these tests.' }, () => {
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
    artifact_name: 'issue-routing-issue-42',
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
      GH_AW_WORKFLOW_ID: 'issue-routing',
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
      workflow: 'Issue Routing',
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
    const compiled = readFileSync(resolve(__dirname, '../workflows/issue-routing.lock.yml'), 'utf8');
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

  it('guards the pinned type publisher before any write, while preserving Feature updates', async () => {
    const compiled = readFileSync(resolve(__dirname, '../workflows/issue-routing.lock.yml'), 'utf8');
    const config = JSON.parse(JSON.parse(compiled.match(/GH_AW_SAFE_OUTPUTS_HANDLER_CONFIG: (.+)/)[1])).set_issue_type;
    const { main: typePublisher } = require(resolve(runtime, 'set_issue_type.cjs'));
    global.github.rest.issues.update = async request => { requests.push(request); return { data: {} }; };
    global.github.rest.issues.get = async () => ({ data: { node_id: 'issue-42' } });
    global.github.graphql = async (query, variables) => {
      if (query.includes('query(')) {
        return { repository: { issueTypes: { nodes: [{ id: 'feature-type', name: 'Feature' }] } } };
      }
      requests.push(variables);
      return {};
    };
    const publish = async items => {
      validateRequests({ items });
      for (const item of items) {
        const handler = item.type === 'add_comment' ? await main(configuredComment())
          : await typePublisher({ ...config, target: '42' });
        const result = await handler(item);
        assert.equal(result.success, true, result.error);
      }
    };
    for (const issue_type of ['', undefined, null, 'Bug']) {
      await assert.rejects(publish([
        { type: 'add_comment', body: comment() },
        { type: 'set_issue_type', issue_type },
      ]), /only set.*Feature/);
      assert.equal(requests.length, 0);
    }
    await publish([{ type: 'set_issue_type', issue_type: 'Feature', issue_number: 999 }]);
    assert.equal(requests.length, 1);
    assert.equal(requests[0].issueId, 'issue-42');
    assert.equal(requests[0].issueType.issueTypeId, 'feature-type');
  });

  function checkArtifactUpload(confirmed) {
    const directory = mkdtempSync(join(tmpdir(), 'issue-routing-upload-'));
    try {
      const staging = join(directory, 'evidence');
      for (const issue of ['42', '43']) {
        mkdirSync(join(staging, `issue-routing-issue-${issue}`), { recursive: true });
        writeFileSync(join(staging, `issue-routing-issue-${issue}`, 'report.md'), 'Observed failure.');
      }
      const evidence = join(staging, 'issue-routing-issue-42');
      const historical = { ...record, run_url: record.run_url.replace('/123', '/100'), commit: 'b'.repeat(40) };
      mkdirSync(join(evidence, 'history', '100'), { recursive: true });
      writeFileSync(join(evidence, 'history', '100', 'reproduction.json'), JSON.stringify(historical, null, 2));
      writeFileSync(join(evidence, 'report.md'), confirmed
        ? 'Current run: reproduced. Retained earlier evidence from run 100.'
        : 'Current run: inconclusive. Retained earlier evidence from run 100; no new reproduction.');
      if (confirmed) writeFileSync(join(evidence, 'reproduction.json'), JSON.stringify(record, null, 2));
      const copy = join(directory, 'temporary-copy');
      const final = join(directory, 'checked-final');
      assert.equal(checkEvidenceFiles({ source: evidence, destination: copy, core: global.core }), true);
      assert.equal(checkEvidenceFiles({ source: copy, destination: final, core: global.core }), true);
      assert.deepEqual(JSON.parse(readFileSync(join(final, 'history', '100', 'reproduction.json'), 'utf8')), historical);
      if (confirmed) assert.deepEqual(JSON.parse(readFileSync(join(final, 'reproduction.json'), 'utf8')), record);
      assert.equal(readFileSync(join(final, 'report.md'), 'utf8'), readFileSync(join(evidence, 'report.md'), 'utf8'));
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  }

  for (const confirmed of [true, false]) {
    it(`preserves a ${confirmed ? 'newly reproduced' : 'retained-only'} evidence folder through both evidence checks`,
      () => checkArtifactUpload(confirmed));
  }
});
