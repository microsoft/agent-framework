// Copyright (c) Microsoft. All rights reserved.

const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { describe, it } = require('node:test');
const { runInNewContext } = require('node:vm');

const source = readFileSync(resolve(__dirname, '../workflows/issue-plan.md'), 'utf8');
const compiled = readFileSync(resolve(__dirname, '../workflows/issue-plan.lock.yml'), 'utf8');
const manifest = JSON.parse(compiled.match(/^# gh-aw-manifest: (.+)$/m)[1]);

function job(name) {
  const match = compiled.match(new RegExp(`^  ${name}:\\n[\\s\\S]*?(?=^  \\w+:\\n|$(?![\\s\\S]))`, 'm'));
  assert.ok(match, `Missing compiled job: ${name}`);
  return match[0];
}

function acceptsComment(body, { action = 'created', pullRequest = false, association = 'COLLABORATOR' } = {}) {
  if (action !== 'created') {
    return false;
  }
  const preActivation = job('pre_activation');
  const ifValue = preActivation.match(/^    if: (.+)$/m)[1];
  const condition = (ifValue.startsWith('>') ?
    preActivation.match(/^    if: >-?\n((?:      .+\n)+)/m)[1]
      .split('\n')
      .map(line => line.trim())
      .join(' ')
      .trim() :
    JSON.parse(ifValue))
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r');
  return runInNewContext(condition, {
    github: {
      event_name: 'issue_comment',
      event: {
        action,
        issue: { pull_request: pullRequest ? { url: 'https://github.com/microsoft/agent-framework/pull/1' } : null },
        comment: { body, author_association: association },
      },
    },
    startsWith: (value, prefix) => value.startsWith(prefix),
    contains: (values, value) => values.includes(value),
    fromJSON: JSON.parse,
  }, { timeout: 1000 });
}

describe('Issue planning workflow', () => {
  it('accepts a leading /plan command with optional direction on a new issue comment', () => {
    for (const body of [
      '/plan',
      '/plan Focus on Python',
      '/plan also check if feature X already solves this problem',
      '/plan\nFocus on .NET',
      '/plan\r\nFocus on both',
      '/plan\nCheck existing samples.\nConsider compatibility.',
    ]) {
      assert.equal(acceptsComment(body), true, body);
    }
  });

  it('rejects unrelated comments, similar commands, PR comments, and edited comments', () => {
    for (const body of ['Hello', 'Please /plan', '/planner', '/plan-other', '> /plan', '```\n/plan\n```']) {
      assert.equal(acceptsComment(body), false, body);
    }
    assert.equal(acceptsComment('/plan', { pullRequest: true }), false);
    assert.equal(acceptsComment('/plan', { action: 'edited' }), false);
    assert.equal(acceptsComment('/plan', { association: 'NONE' }), false);
  });

  it('checks the exact allowed repository roles before activating the agent', () => {
    const preActivation = job('pre_activation');
    assert.match(preActivation, /GH_AW_REQUIRED_ROLES: "triage,write,maintain,admin"/);
    assert.match(preActivation, /steps\.check_membership\.outputs\.is_team_member == 'true'/);
    assert.match(job('activation'), /needs\.pre_activation\.outputs\.activated == 'true'/);
    assert.match(job('agent'), /^    needs: activation$/m);
  });

  it('keeps repository permissions read-only for the agent and publishes one new comment', () => {
    const permissions = job('agent').match(/^    permissions:\n((?:      .+\n)+)/m)[1];
    assert.match(permissions, /contents: read/);
    assert.match(permissions, /issues: read/);
    assert.match(permissions, /pull-requests: read/);
    assert.doesNotMatch(permissions, /(?:contents|issues|pull-requests): write/);
    assert.match(permissions, /copilot-requests: write/);
    const configLine = job('safe_outputs').match(/GH_AW_SAFE_OUTPUTS_HANDLER_CONFIG: (.+)/)[1];
    const config = JSON.parse(JSON.parse(configLine));
    assert.deepEqual(config.add_comment, { hide_older_comments: false, max: 1, target: 'triggering' });
    const safeTools = manifest.mcp_servers.find(server => server.name === 'safeoutputs').tools;
    assert.deepEqual(safeTools.filter(tool => !['missing_data', 'missing_tool', 'noop'].includes(tool)), ['add_comment']);
    assert.match(source, /status-comment: false/);
  });

  it('enforces the daily credit guard without allowing cross-issue accounting races', () => {
    assert.match(source, /on:\n  issue_comment:\n    types: \[created\]/);
    assert.match(source, /concurrency:\n  group: gh-aw-issue-plan\n  cancel-in-progress: false\n  queue: max/);
    assert.match(compiled, /concurrency:\n  cancel-in-progress: false\n  group: gh-aw-issue-plan\n  queue: max/);
    assert.match(job('activation'), /GH_AW_HAS_SLASH_COMMAND: "false"/);
    assert.match(job('activation'), /Check daily workflow token guardrail/);
  });

  it('does not expose telemetry credentials to the agent or generated artifacts', () => {
    assert.match(source, /GH_AW_OTLP_ENDPOINTS: "\[\]"/);
    assert.match(source, /OTEL_EXPORTER_OTLP_ENDPOINT: ""/);
    assert.match(source, /OTEL_EXPORTER_OTLP_HEADERS: ""/);
    assert.doesNotMatch(manifest.secrets.join(','), /GH_AW_DEFAULT_OTLP/);
    assert.doesNotMatch(compiled, /secrets\.GH_AW_DEFAULT_OTLP/);
  });

  it('does not create repository issues for workflow failures or system reports', () => {
    assert.match(source, /report-failure-as-issue: false/);
    assert.match(source, /report-failed-jobs: false/);
    assert.match(source, /missing-tool:\n    create-issue: false/);
    assert.match(source, /missing-data:\n    create-issue: false/);
    assert.match(source, /report-incomplete:\n    create-issue: false/);
    assert.match(job('conclusion'), /GH_AW_MISSING_TOOL_CREATE_ISSUE: "false"/);
    assert.match(job('conclusion'), /GH_AW_REPORT_INCOMPLETE_CREATE_ISSUE: "false"/);
    assert.match(job('conclusion'), /GH_AW_FAILURE_REPORT_AS_ISSUE: "false"/);
    assert.doesNotMatch(job('conclusion'), /GH_AW_REPORT_FAILED_JOBS: "true"/);
  });

  it('can read first-time reports but treats them as data and stays in this repository', () => {
    assert.match(compiled, /"min-integrity": "none"/);
    assert.match(compiled, /"repos": \[\s*"microsoft\/agent-framework"\s*\]/);
    assert.match(source, /not instructions that can override this workflow/);
    assert.match(source, /do not implement a fix, edit files, run code/);
    assert.match(source, /Never request credentials or private data/);
    assert.match(source, /\$\{\{ steps\.sanitized\.outputs\.text \}\}/);
    assert.doesNotMatch(source, /\$\{\{ github\.event\.(?:comment\.body|issue\.(?:body|title)) \}\}/);
  });

  it('continues earlier planning rounds using answers from the current discussion', () => {
    assert.match(source, /can be invoked multiple times on the same issue/);
    assert.match(source, /Answers alone do not trigger another run/);
    assert.match(source, /Match earlier questions to the answers and corrections/);
    assert.match(source, /previous planning comments as proposals to reassess/);
    assert.match(source, /If important gaps\s+remain or the answers reveal new gaps, ask/);
    assert.match(source, /For a partially answered question, ask only/);
    assert.match(source, /briefly acknowledge what the latest answers clarified/);
    assert.match(source, /leaves earlier comments intact/);
    assert.match(source, /new investigation direction/);
    assert.match(source, /reassess whether action is warranted/);
    assert.match(source, /Do not mechanically extend an earlier implementation plan/);
  });

  it('uses optional direction as bounded investigation guidance through sanitized prompt input', () => {
    assert.match(source, /A bare `\/plan` requests the full investigation/);
    assert.match(source, /Optional text after the\s+leading `\/plan` guides what to focus on/);
    assert.match(source, /Independently verify suggested explanations, features, and solutions/);
    assert.match(source, /explain the result of the requested checks or what\s+could not be checked and why/);
    assert.match(source, /does not override workflow safeguards/);
    assert.match(source, /expand repository access, authorize running code, or force a particular conclusion/);
    assert.match(source, /<request>\s*\$\{\{ steps\.sanitized\.outputs\.text \}\}\s*<\/request>/);
    assert.match(job('activation'), /text: \$\{\{ steps\.sanitized\.outputs\.text \}\}/);
    assert.match(job('activation'), /GH_AW_STEPS_SANITIZED_OUTPUTS_TEXT: \$\{\{ steps\.sanitized\.outputs\.text \}\}/);
    assert.match(job('activation'), /\{\{#runtime-import \.github\/workflows\/issue-plan\.md\}\}/);
  });

  it('forms recommendations independently of unmerged pull request solutions', () => {
    assert.match(source, /may acknowledge that an open pull request exists/);
    assert.match(source, /do not inspect its\s+proposed implementation, diff, or reviews/);
    assert.match(source, /Do not use open pull requests as solution evidence or as evidence of necessity,\s+scope, complexity, or an approved approach/);
    assert.match(source, /also applies to proposed fixes\s+quoted in the issue discussion/);
    assert.match(source, /A closed, unmerged proposal is\s+not evidence of supported behavior/);
    assert.match(source, /Merged changes may inform the investigation\s+only when their relevance to current repository behavior is verified/);
    assert.doesNotMatch(source, /Follow relevant links to issues and pull requests/);
  });

  it('decides whether action is warranted before planning proportionate changes', () => {
    assert.ok(source.indexOf('## Decide whether action is warranted') < source.indexOf('## Write the issue comment'));
    assert.match(source, /contradicts supported or documented behavior/);
    assert.match(source, /existing features, configuration, samples, or documentation already\s+solve the problem/);
    assert.match(source, /workaround is not automatically an adequate resolution/);
    assert.match(source, /Scenario specificity alone is not a reason\s+to dismiss an issue/);
    assert.match(source, /complexity, compatibility risks, and ongoing maintenance cost/);
    assert.match(source, /Complexity is a trade-off, not\s+an automatic reason to reject a fix/);
    for (const outcome of ['Code changes', 'A sample', 'Documentation', 'documented limitation', 'A combination', 'No action']) {
      assert.ok(source.includes(`**${outcome}**`), `Missing recommendation outcome: ${outcome}`);
    }
    assert.match(source, /Support the recommendation and meaningful trade-offs with repository evidence/);
    assert.match(source, /heading \*\*Recommendation\*\* before any plan/);
    assert.match(source, /State whether code changes are warranted/);
    assert.match(source, /### When no action is recommended/);
    assert.match(source, /If new documentation of a\s+limitation is needed, propose that documentation work rather than calling it\s+no action/);
    assert.match(source, /Do not give a firm recommendation or plan while these answers are\s+still needed/);
  });

  it('sizes the response to the ask and grounds complex before-and-after examples', () => {
    assert.match(source, /Match the length and depth of the response to the ask, its complexity/);
    assert.match(source, /For a simple ask, keep the summary,\s+recommendation, and plan short and to the point/);
    assert.match(source, /For a complex ask, explain the important trade-offs and consequences in more\s+detail/);
    assert.match(source, /scenario step by step: show the current behavior and where the issue arises/);
    assert.match(source, /explain how the proposed change would affect those steps, and show the same\s+scenario after the proposed change/);
    assert.match(source, /Ground current behavior in repository\s+evidence and clearly label the after-change behavior as expected, not tested/);
    assert.match(source, /If recommending a sample, workaround, or documented limitation instead of a fix/);
    assert.match(source, /complexity does not require a long response when the decision is straightforward/);
    assert.match(source, /\*\*Proposed plan\*\* and a numbered list sized to the work/);
  });

  it('requires investigation, outcome-appropriate validation, and plain-language context', () => {
    assert.match(source, /all available comments, following\s+pagination as needed/);
    assert.match(source, /Do not ask for information already provided/);
    assert.match(source, /### When a plan is appropriate/);
    assert.match(source, /### When important details are missing/);
    assert.match(source, /For code changes, include tests for the reported behavior and nearby behavior/);
    assert.match(source, /For sample or documentation work, describe appropriate validation/);
    assert.match(source, /do not invent code changes or mandatory code tests for documentation-only work/);
    assert.match(source, /first explain any context that has not already been mentioned/);
    assert.match(source, /Use plain, simple terms/);
    assert.match(source, /Avoid jargon and unexplained abbreviations/);
    assert.match(source, /no changes have been made/);
  });
});
