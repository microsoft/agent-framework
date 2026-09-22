// Copyright (c) Microsoft. All rights reserved.

const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { describe, it } = require('node:test');
const { resolve } = require('node:path');

const workflow = readFileSync(resolve(__dirname, '../workflows/devflow-fix-ci.yml'), 'utf8');

describe('DevFlow PR repair entrypoint', () => {
  it('does not let unrelated comments evict an accepted repair run', () => {
    const workflowHeader = workflow.slice(0, workflow.indexOf('\njobs:'));
    assert.doesNotMatch(workflowHeader, /^concurrency:/m);
  });

  it('keeps authorization and private checkout in the source repository workflow', () => {
    const team = workflow.indexOf('Authorize the frozen command requester');
    const checkout = workflow.indexOf('Checkout authorized DevFlow controller');
    const intake = workflow.indexOf('Validate and bind the authorized request');
    assert.ok(team > 0 && checkout > team && intake > checkout);
    assert.match(workflow, /repository: \$\{\{ env\.DEVFLOW_REPOSITORY \}\}/);
    assert.match(workflow, /token: \$\{\{ secrets\.DEVFLOW_TOKEN \}\}/);
    assert.doesNotMatch(workflow, /createDispatchEvent|repository_dispatch/);
  });

  it('acknowledges only a validated repair request', () => {
    const intake = workflow.indexOf('Validate and bind the authorized request');
    const reaction = workflow.indexOf('Acknowledge accepted repair command');
    assert.ok(reaction > intake);
    assert.match(workflow, /steps\.intake\.outputs\.mode == 'repair'/);
    assert.match(workflow, /content: 'eyes'/);
  });

  it('runs private policy code and preserves the exact-diff publication gate', () => {
    assert.match(workflow, /scripts\/trigger_fix_ci\.py --phase run/);
    assert.match(workflow, /environment: devflow-pr-repair-publish/);
    assert.match(workflow, /environment: github-app-auth/);
    assert.match(workflow, /scripts\/trigger_fix_ci\.py --phase validate-publication/);
    assert.match(workflow, /contents-permission: write/);
    assert.match(workflow, /steps\.run\.outputs\.patch_sha256/);
  });
});
