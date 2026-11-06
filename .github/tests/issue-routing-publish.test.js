// Copyright (c) Microsoft. All rights reserved.

const assert = require('node:assert/strict');
const fs = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const { afterEach, beforeEach, describe, it } = require('node:test');
const { checkPublication, validateRequests } = require('../scripts/issue-routing-publish.js');

describe('Issue routing publication checks', () => {
  let directory;
  let input;
  let outputs;
  let notices;
  beforeEach(() => {
    directory = fs.mkdtempSync(join(tmpdir(), 'routing-publish-'));
    outputs = {};
    notices = [];
    input = {
      issueNumber: '42',
      outputPath: join(directory, 'agent_output.json'),
      context: { repo: { owner: 'microsoft', repo: 'agent-framework' } },
      core: {
        setOutput: (name, value) => { outputs[name] = value; },
        notice: message => notices.push(message),
      },
      github: { rest: { issues: { get: async params => {
        assert.deepEqual(params, { owner: 'microsoft', repo: 'agent-framework', issue_number: 42 });
        return { data: { number: 42, labels: [] } };
      } } } },
    };
    fs.writeFileSync(input.outputPath, JSON.stringify({
      items: [{ type: 'add_comment', body: 'Finding' }, { type: 'set_issue_type', issue_type: 'Feature' }],
    }));
  });
  afterEach(() => fs.rmSync(directory, { recursive: true, force: true }));

  it('permits valid updates without rewriting them', async () => {
    const original = fs.readFileSync(input.outputPath, 'utf8');
    await checkPublication(input);
    assert.equal(outputs.allowed, 'true');
    assert.equal(fs.readFileSync(input.outputPath, 'utf8'), original);
  });

  it('rejects empty, missing, null, and unapproved type changes before publishing any request', () => {
    for (const issue_type of ['', undefined, null, 'Bug', 'feature', 0]) {
      assert.throws(() => validateRequests({
        items: [{ type: 'add_comment', body: 'Finding' }, { type: 'set_issue_type', issue_type }],
      }), /only set.*Feature/);
    }
    for (const output of [{}, { items: null }, { items: [null] }]) {
      assert.throws(() => validateRequests(output), /items array|Invalid/);
    }
  });

  it('replaces every queued write with an explicit no-op when current labels stop publication', async () => {
    for (const labels of [['spam'], ['suspected-spam', 'safe-to-triage'], [{ name: 'NEEDS-MAINTAINER-TRIAGE' }]]) {
      input.github.rest.issues.get = async () => ({ data: { number: 42, labels } });
      await checkPublication(input);
      assert.equal(outputs.allowed, 'false');
      const { items } = JSON.parse(fs.readFileSync(input.outputPath, 'utf8'));
      assert.equal(items.length, 1);
      assert.equal(items[0].type, 'noop');
      assert.match(notices.at(-1), /Skipping routing publication/);
    }
  });

  it('checks again after evidence preparation, even if the first check allowed updates', async () => {
    await checkPublication(input);
    assert.equal(outputs.allowed, 'true');
    input.github.rest.issues.get = async () => ({
      data: { number: 42, labels: ['spam', 'safe-to-triage'] },
    });
    await checkPublication(input);
    assert.equal(outputs.allowed, 'false');
    assert.equal(JSON.parse(fs.readFileSync(input.outputPath, 'utf8')).items[0].type, 'noop');
  });

  it('allows a released review hold, but does not hide API, identity, or input errors', async () => {
    input.github.rest.issues.get = async () => ({
      data: { number: 42, labels: ['needs-maintainer-triage', 'safe-to-triage'] },
    });
    await checkPublication(input);
    assert.equal(outputs.allowed, 'true');
    input.github.rest.issues.get = async () => { throw new Error('Access denied'); };
    await assert.rejects(checkPublication(input), /Access denied/);
    assert.equal(outputs.allowed, 'false');
    input.github.rest.issues.get = async () => ({ data: { number: 42, pull_request: {} } });
    await assert.rejects(checkPublication(input), /not a pull request/);
    await assert.rejects(checkPublication({ ...input, issueNumber: '0' }), /positive, safe integer/);
    fs.writeFileSync(input.outputPath, 'invalid');
    await assert.rejects(checkPublication(input), SyntaxError);
  });
});
