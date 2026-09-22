// Copyright (c) Microsoft. All rights reserved.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const workflow = name => fs.readFileSync(path.join(__dirname, '../workflows', name), 'utf8');
const main = workflow('devflow-fix-ci.yml');
const controller = workflow('devflow-repair-controller.yml');
const verification = workflow('devflow-repair-verification.yml');
const pipeline = workflow('devflow-repair-pipeline.yml');
const publisher = workflow('devflow-repair-publish.yml');
function job(yaml, name) {
  const start = yaml.indexOf(`\n  ${name}:\n`);
  assert.ok(start >= 0, `missing ${name}`);
  return yaml.slice(start + 1).split(/\n(?=  [a-zA-Z_][a-zA-Z_0-9]*:\n)/)[0];
}

test('freezes public input and authorizes membership before touching private controller credentials', () => {
  const snapshot = job(main, 'public_snapshot');
  assert.match(snapshot, /author_association == 'MEMBER'/);
  assert.match(snapshot, /author_association == 'OWNER'/);
  assert.match(snapshot, /parseCommand\(context.payload.comment.body\)/);
  assert.match(snapshot, /cancel-in-progress: false/);
  assert.doesNotMatch(snapshot, /secrets\.|DEVFLOW_TOKEN|getCommit|github-token:/);
  assert.doesNotMatch(job(main, 'team_check'), /DEVFLOW_TOKEN/);
  assert.match(job(main, 'authorized_controller'), /needs.team_check.outputs.permitted == 'true'/);
  assert.match(job(main, 'authorized_controller'), /bindController/);
});

test('verification runs on an ephemeral runner with no inherited repository or service credentials', () => {
  assert.match(verification, /runs-on: ubuntu-latest/);
  assert.match(verification, /permissions: \{\}/);
  assert.doesNotMatch(verification, /secrets:|secrets\.|GH_TOKEN|GITHUB_TOKEN|DEVFLOW_TOKEN|copilot-requests|id-token|environment:/);
  assert.doesNotMatch(verification, /actions\/checkout|github-token:/);
  assert.match(verification, /credential.helper= fetch/);
  assert.match(verification, /verify_pr_repair\.py/);
  assert.match(verification, /--request-sha256/);
  assert.doesNotMatch(verification, /candidate\.json|candidate\.diff/);
  for (let i = 1; i <= 5; i++) {
    const verifier = job(pipeline, `verifier_${i}`);
    assert.match(verifier, /permissions: \{\}/);
    assert.doesNotMatch(verifier, /secrets:/);
    assert.match(verifier, new RegExp(`needs.controller_${i - 1}.outputs.request_sha256`));
  }
});

test('controller stages keep write authority out and bind immutable predecessor evidence', () => {
  assert.match(controller, /contents-permission: read/);
  assert.match(controller, /issues-permission: read/);
  assert.match(controller, /pull-requests-permission: read/);
  assert.doesNotMatch(controller, /contents-permission: write|issues: write|docker|pytest|dotnet test/);
  assert.match(controller, /decodeBound/);
  assert.match(controller, /ref: \$\{\{ inputs.devflow_sha \}\}/);
  assert.match(controller, /artifact-ids: \$\{\{ inputs.state_artifact_id \}\}/);
  assert.match(controller, /--state-sha256/);
  assert.match(controller, /--verification-sha256/);
  assert.match(controller, /--phase controller/);
  for (let i = 0; i <= 5; i++) assert.match(pipeline, new RegExp(`controller_${i}:`));
});

test('only the separate publisher obtains write authority after validation', () => {
  assert.match(publisher, /devflow-pr-repair-publish/);
  assert.match(publisher, /devflow-ci-publish/);
  assert.match(publisher, /DEVELOPER_TEAM:/);
  assert.match(publisher, /DEVFLOW_APPROVAL_ENVIRONMENT:/);
  assert.match(publisher, /--candidate-sha256/);
  assert.ok(publisher.indexOf('--phase validate-publication') < publisher.indexOf('id: write-auth'));
  assert.ok(publisher.indexOf('id: write-auth') < publisher.indexOf('--phase publish'));
  assert.doesNotMatch(publisher, /docker|pytest|dotnet test|DEVFLOW_MODEL_TOKEN/);
  assert.match(publisher, /contents-permission: write/);
  for (const yaml of [main, controller, publisher]) {
    assert.doesNotMatch(yaml, /fallback-token|GH_ACTIONS_PR_WRITE|vars.GH_APP_AUTH_MODE/);
    assert.match(yaml, /mode: app/);
  }
});

test('reporter exposes exact diff approval token before entering publication gate', () => {
  assert.match(pipeline, /patch-sha256:\$\{process.env.PATCH_SHA256\}/);
  assert.match(pipeline, /read\('candidate.diff', process.env.PATCH_SHA256/);
  assert.match(pipeline, /read\('candidate.json', process.env.CANDIDATE_SHA256/);
  assert.match(pipeline, /needs: \[select_result, report\]/);
  assert.match(job(pipeline, 'report'), /issues: write/);
  assert.doesNotMatch(job(pipeline, 'report'), /secrets\.|DEVFLOW_TOKEN|id-token|private controller/);
});

test('external actions remain pinned and downloads select immutable artifact IDs', () => {
  for (const yaml of [main, controller, verification, pipeline, publisher]) {
    for (const match of yaml.matchAll(/uses: ([^\n]+)/g)) {
      assert.ok(match[1].startsWith('./') || /@[0-9a-f]{40}(?:\s|$)/.test(match[1]), match[1]);
    }
    for (const block of yaml.split(/\n      - /)) {
      if (block.includes('uses: actions/download-artifact@')) assert.match(block, /artifact-ids:/);
    }
  }
});
