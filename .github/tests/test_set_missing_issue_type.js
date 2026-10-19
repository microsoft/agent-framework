// Copyright (c) Microsoft. All rights reserved.

const { it } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const setMissingIssueType = require('../scripts/set_missing_issue_type.js');

function createMocks(issue) {
  const updates = [];
  const context = {
    repo: { owner: 'microsoft', repo: 'agent-framework' },
    issue: { number: 123 },
    // An opened event can be stale by the time the workflow runs.
    payload: { issue: { title: 'Python: [Bug]: original title', type: null } },
  };
  const github = { rest: { issues: {
    get: async (params) => {
      assert.deepEqual(params, { ...context.repo, issue_number: 123 });
      return { data: issue };
    },
    update: async (params) => { updates.push(params); },
  } } };
  return { github, context, core: { info() {} }, updates };
}

for (const [title, type] of [
  ['Python: [Bug]: broken', 'Bug'],
  ['.NET: [Bug]: broken', 'Bug'],
  ['[Bug]: broken', 'Bug'],
  ['[Feature]: new capability', 'Feature'],
  ['Python: [Feature]: new capability', 'Feature'],
  ['.NET: [Feature]: new capability', 'Feature'],
  [' python: [bug]: broken', 'Bug'],
]) {
  it(`sets ${type} for ${title}`, async () => {
    const mocks = createMocks({ title, type: null });
    await setMissingIssueType(mocks);
    assert.deepEqual(mocks.updates, [{ ...mocks.context.repo, issue_number: 123, type }]);
  });
}

for (const type of [{ name: 'Bug' }, { name: 'Feature' }, { name: 'Task' }]) {
  it(`preserves an existing ${type.name} despite a stale blank event`, async () => {
    const mocks = createMocks({ title: 'Python: [Bug]: broken', type });
    await setMissingIssueType(mocks);
    assert.deepEqual(mocks.updates, []);
  });
}

for (const title of ['Python: [Question]: help', 'Discuss [Bug]: title format', 'Bug report', '', null]) {
  it(`leaves an unrecognized current title unchanged: ${title}`, async () => {
    const mocks = createMocks({ title, type: null });
    await setMissingIssueType(mocks);
    assert.deepEqual(mocks.updates, []);
  });
}

it('propagates API failures so the workflow reports the failure', async () => {
  const mocks = createMocks({ title: '[Bug]: broken', type: null });
  mocks.github.rest.issues.update = async () => { throw new Error('API unavailable'); };
  await assert.rejects(setMissingIssueType(mocks), /API unavailable/);
});

for (const failingMethod of ['get', 'update']) {
  it(`finishes workflow label assignment before a fallback ${failingMethod} failure`, async () => {
    const workflow = readFileSync(path.join(__dirname, '../workflows/label-issues.yml'), 'utf8');
    // Execute the actual github-script steps in workflow order, with API mocks.
    const scripts = [...workflow.matchAll(/^          script: \|\n((?:^            .*\n|^\n)+)/gm)]
      .map((match) => match[1].replace(/^            /gm, ''));
    assert.equal(scripts.length, 2);
    const mocks = createMocks({ title: 'Python: [Bug]: broken', type: null });
    const calls = [];
    mocks.github.rest.issues.addLabels = async ({ labels }) => {
      await new Promise((resolve) => setImmediate(resolve));
      assert.deepEqual(labels, ['triage', 'python']);
      calls.push('labels completed');
    };
    mocks.github.rest.issues[failingMethod] = async () => {
      calls.push('fallback failed');
      throw new Error('API unavailable');
    };
    const requireScript = (name) => name.endsWith('check_team_membership.js')
      ? async () => ({ isTeamMember: false })
      : setMissingIssueType;
    const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
    const runSteps = async () => {
      for (const script of scripts) {
        await new AsyncFunction('github', 'context', 'core', 'require', script)(
          mocks.github, mocks.context, mocks.core, requireScript,
        );
      }
    };
    await assert.rejects(runSteps(), /API unavailable/);
    assert.deepEqual(calls, ['labels completed', 'fallback failed']);
  });
}
