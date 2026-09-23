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

  it('uses the review-proven App grant and the job token for Actions reads', () => {
    assert.doesNotMatch(workflow, /actions-permission: read/);
    assert.ok([...workflow.matchAll(/GITHUB_TOKEN: \$\{\{ github\.token \}\}/g)].length >= 3);
    const authorization = workflow.slice(
      workflow.indexOf('Get source-repository App token'),
      workflow.indexOf('Authorize the frozen command requester'),
    );
    assert.match(authorization, /contents-permission: read/);
    assert.match(authorization, /issues-permission: write/);
    assert.match(authorization, /pull-requests-permission: read/);

    const repair = workflow.slice(workflow.indexOf('\n  repair:'), workflow.indexOf('\n  approve:'));
    assert.match(repair, /permissions:\n      contents: read\n      actions: read\n      checks: read/);
    assert.doesNotMatch(repair.slice(0, repair.indexOf('    outputs:')), /issues: write/);
    const repairRead = repair.slice(
      repair.indexOf('Get read-only source-repository App token'),
      repair.indexOf('Generate and verify the bounded repair'),
    );
    assert.match(repairRead, /contents-permission: read/);
    assert.match(repairRead, /issues-permission: read/);
    assert.match(repairRead, /pull-requests-permission: read/);

    const publish = workflow.slice(workflow.indexOf('\n  publish:'));
    assert.doesNotMatch(publish.slice(0, publish.indexOf('    env:')), /issues: write/);
    const publishRead = publish.slice(
      publish.indexOf('Get read-only source-repository App token'),
      publish.indexOf('Revalidate exact candidate and approval before write authority'),
    );
    assert.match(publishRead, /issues-permission: read/);
    assert.match(publishRead, /pull-requests-permission: read/);
    const publishWrite = publish.slice(publish.indexOf('Get source-repository write token'));
    assert.match(publishWrite, /contents-permission: write/);
    assert.match(publishWrite, /issues-permission: write/);
    assert.match(publishWrite, /pull-requests-permission: read/);
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
