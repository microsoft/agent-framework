// Copyright (c) Microsoft. All rights reserved.

const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { describe, it } = require('node:test');
const { runInNewContext } = require('node:vm');

const workflow = readFileSync(resolve(__dirname, '../workflows/dotnet-build-and-test.yml'), 'utf8');
const jobs = [...workflow.matchAll(/^  ([\w-]+):\n([\s\S]*?)(?=^  [\w-]+:\n|$(?![\s\S]))/gm)]
  .map(([, name, source]) => ({ name, source }));

function selected(job, eventName, ref = 'refs/heads/main', changes = 'true') {
  const condition = job.source.match(/^    if: (.+)$/m);
  assert.ok(condition, `Missing job condition: ${job.name}`);
  return runInNewContext(condition[1].replaceAll('needs.paths-filter', 'needs.pathsFilter'), {
    github: { event_name: eventName, ref },
    needs: { pathsFilter: { outputs: { dotnetChanges: changes, foundryHostingChanges: changes } } },
    startsWith: (value, prefix) => value.startsWith(prefix),
  }, { timeout: 1000 });
}

describe('.NET build and test workflow', () => {
  it('does not select integration jobs for pull requests or merge groups', () => {
    const integrationJobs = jobs.filter(job => /id-token: ["']?write/.test(job.source));
    assert.deepEqual(integrationJobs.map(job => job.name), [
      'dotnet-integration-test',
      'dotnet-foundry-hosted-it',
    ]);
    for (const job of integrationJobs) {
      for (const eventName of ['merge_group', 'pull_request', 'pull_request_target', 'workflow_run']) {
        assert.equal(selected(job, eventName), false, `${job.name}: ${eventName}`);
      }
    }
  });

  it('keeps unit checks available without integration job permissions or environment', () => {
    const unitJob = jobs.find(job => job.name === 'dotnet-test');
    assert.ok(unitJob);
    for (const eventName of ['pull_request', 'merge_group', 'push', 'schedule', 'workflow_dispatch']) {
      assert.equal(selected(unitJob, eventName), true, eventName);
    }
    assert.equal(/id-token:|^    environment:/m.test(unitJob.source), false);
  });

  it('selects integration jobs only for supported events on configured branches', () => {
    const integrationJobs = jobs.filter(job => /id-token: ["']?write/.test(job.source));
    assert.ok(integrationJobs.length > 0);
    for (const job of integrationJobs) {
      for (const eventName of ['push', 'schedule', 'workflow_dispatch']) {
        for (const ref of ['refs/heads/main', 'refs/heads/feature/test']) {
          assert.equal(selected(job, eventName, ref), true, `${job.name}: ${eventName} ${ref}`);
          assert.equal(selected(job, eventName, ref, 'false'), false, `${job.name}: no changes`);
        }
        for (const ref of ['refs/heads/other', 'refs/heads/gh-readonly-queue/main/pr-1', 'refs/tags/main']) {
          assert.equal(selected(job, eventName, ref), false, `${job.name}: ${eventName} ${ref}`);
        }
      }
    }
  });

  it('selects unit, integration, and coverage steps from each job matrix', () => {
    const unitJob = jobs.find(job => job.name === 'dotnet-test');
    const integrationJob = jobs.find(job => job.name === 'dotnet-integration-test');
    assert.ok(unitJob);
    assert.ok(integrationJob);
    assert.match(unitJob.source, /steps: &dotnet-test-steps/);
    assert.match(integrationJob.source, /steps: \*dotnet-test-steps/);
    assert.equal([...unitJob.source.matchAll(/integration-tests: false/g)].length, 2);
    assert.equal([...integrationJob.source.matchAll(/integration-tests: true/g)].length, 2);
    for (const [name, integrationOnly] of [
      ['Azure CLI Login', true],
      ['Run Integration Tests', true],
      ['Upload integration test results', true],
      ['Run Unit Tests', false],
      ['Generate test reports', false],
      ['Upload coverage report artifact', false],
      ['Check coverage', false],
    ]) {
      const step = unitJob.source.split(`      - name: ${name}\n`)[1]?.split('\n      - ')[0];
      assert.ok(step, `Missing step: ${name}`);
      const condition = step.match(/^        if: (.+)$/m);
      assert.ok(condition, `Missing step condition: ${name}`);
      const expression = condition[1]
        .replace(/^\$\{\{|\}\}$/g, '')
        .replaceAll('matrix.integration-tests', 'matrix.integrationTests');
      for (const integrationTests of [false, true]) {
        const result = runInNewContext(expression, {
          matrix: { integrationTests, targetFramework: 'net10.0' },
          env: { COVERAGE_FRAMEWORK: 'net10.0' },
          always: () => true,
        }, { timeout: 1000 });
        assert.equal(result, integrationTests === integrationOnly, `${name}: ${integrationTests}`);
      }
    }
  });

  it('includes the integration job in the final status and result report', () => {
    const statusJob = jobs.find(job => job.name === 'dotnet-build-and-test-check');
    const reportJob = jobs.find(job => job.name === 'dotnet-integration-test-report');
    assert.ok(statusJob);
    assert.ok(reportJob);
    assert.match(statusJob.source, /needs: \[[^\]\n]*dotnet-integration-test[,\]]/);
    assert.match(reportJob.source, /needs: \[dotnet-integration-test\]/);
    const condition = reportJob.source.match(/^    if: >\n((?:      .+\n)+)/m);
    assert.ok(condition);
    const expression = condition[1].replaceAll('needs.dotnet-integration-test', 'needs.integrationJob');
    for (const result of ['success', 'failure', 'skipped', 'cancelled']) {
      assert.equal(runInNewContext(expression, {
        needs: { integrationJob: { result } },
        always: () => true,
      }, { timeout: 1000 }), ['success', 'failure'].includes(result), result);
    }
  });
});
