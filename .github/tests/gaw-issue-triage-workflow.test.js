// Copyright (c) Microsoft. All rights reserved.

const assert = require('node:assert/strict');
const { existsSync, readFileSync, readdirSync } = require('node:fs');
const { posix, resolve } = require('node:path');
const { describe, it } = require('node:test');

const source = readFileSync(resolve(__dirname, '../workflows/gaw-issue-triage.md'), 'utf8');
const compiled = readFileSync(resolve(__dirname, '../workflows/gaw-issue-triage.lock.yml'), 'utf8');
const owners = readFileSync(resolve(__dirname, '../gaw-issue-triage-owners.yaml'), 'utf8');
const manifest = JSON.parse(compiled.match(/^# gh-aw-manifest: (.+)$/m)[1]);

function job(name) {
  const match = compiled.match(new RegExp(`^  ${name}:\\n[\\s\\S]*?(?=^  \\w+:\\n|$(?![\\s\\S]))`, 'm'));
  assert.ok(match, `Missing compiled job: ${name}`);
  return match[0];
}

function configFor(name, variable) {
  const value = job(name).match(new RegExp(`${variable}: (.+)`))[1];
  return JSON.parse(JSON.parse(value));
}

const handlers = configFor('safe_outputs', 'GH_AW_SAFE_OUTPUTS_HANDLER_CONFIG');

describe('Issue triage workflow', () => {
  it('keeps agentic triage manual-only alongside the legacy workflow', () => {
    const triggers = compiled.match(/^on:\n([\s\S]*?)^permissions:/m)[1];
    assert.match(triggers, /workflow_dispatch:/);
    assert.doesNotMatch(triggers, /^  issues:/m);
    assert.ok(existsSync(resolve(__dirname, '../workflows/issue-triage.yml')));
    assert.equal(existsSync(resolve(__dirname, '../workflows/issue-triage.md')), false);
    assert.equal(existsSync(resolve(__dirname, '../workflows/issue-triage.lock.yml')), false);
    assert.match(source, /name: GAW Issue Triage/);
    const preview = triggers.match(/      preview:\n((?:        .+\n)+)/)[1];
    assert.match(preview, /default: true/);
    assert.match(preview, /required: true/);
    assert.match(preview, /type: boolean/);
    assert.match(job('safe_outputs'), /GH_AW_SAFE_OUTPUTS_STAGED: \$\{\{ github.event_name == 'workflow_dispatch' && inputs.preview \}\}/);
  });

  it('requires trusted preparation without excluding external event actors', () => {
    assert.match(source, /roles: all/);
    assert.match(job('pre_activation'), /^    needs: prepare$/m);
    assert.doesNotMatch(job('pre_activation'), /check_membership|GH_AW_REQUIRED_ROLES/);
    for (const name of ['activation', 'agent']) {
      assert.match(job(name), /needs\.prepare\.outputs\.should_triage == 'true'/);
      assert.match(job(name), /^      - prepare$/m);
    }
    assert.match(job('prepare'), /require\('\.\/\.github\/scripts\/gaw-issue-triage-prepare\.js'\)/);
    assert.match(job('prepare'), /ISSUE_NUMBER: \$\{\{ inputs.issue_number \}\}/);
    assert.doesNotMatch(job('prepare'), /\$\{\{ github\.event\.issue\.(?:body|title) \}\}/);
  });

  it('isolates team credentials and OIDC from the agent and its artifacts', () => {
    const prepare = job('prepare');
    assert.match(prepare, /environment: github-app-auth/);
    assert.match(prepare, /id-token: write/);
    assert.match(prepare, /issues-permission: read/);
    assert.match(prepare, /pull-requests-permission: read/);
    assert.match(prepare, /persist-credentials: false/);
    assert.match(prepare, /TEAM_NAME: \$\{\{ secrets.DEVELOPER_TEAM \}\}/);
    const exported = prepare.match(/^    outputs:\n((?:      .+\n)+)/m)[1];
    assert.deepEqual([...exported.matchAll(/^      (\w+):/gm)].map(match => match[1]).sort(),
      ['issue_number', 'issue_type', 'should_triage']);
    for (const name of ['activation', 'agent', 'detection', 'safe_outputs', 'conclusion']) {
      assert.doesNotMatch(job(name), /secrets\.(?:DEVELOPER_TEAM|GH_APP_|GH_ACTIONS_PR_WRITE|AZURE_|OPENAI_|ANTHROPIC_)/);
      assert.doesNotMatch(job(name), /id-token: write|azure\/login|actions\/cache@/);
    }
    assert.doesNotMatch(compiled, /agent-dashboard|secrets\.GH_AW_DEFAULT_OTLP/);
    assert.match(source, /GH_AW_OTLP_ENDPOINTS: "\[\]"/);
    assert.match(source, /OTEL_EXPORTER_OTLP_HEADERS: ""/);
  });

  it('gives the agent read-only GitHub access and isolated execution tools', () => {
    const permissions = job('agent').match(/^    permissions:\n((?:      .+\n)+)/m)[1];
    for (const permission of ['contents', 'issues', 'pull-requests']) {
      assert.ok(permissions.includes(`${permission}: read`));
    }
    assert.match(permissions, /copilot-requests: write/);
    assert.doesNotMatch(permissions, /(?:contents|issues|pull-requests): write/);
    assert.match(permissions, /actions: read/);
    assert.doesNotMatch(permissions, /actions: write/);
    assert.match(compiled, /"min-integrity": "none"/);
    assert.match(compiled, /"repos": \[\s*"microsoft\/agent-framework"\s*\]/);
    assert.match(job('agent'), /"isolation\\":true/);
    assert.match(source, /allowed: \[defaults, github, python, dotnet\]/);
    assert.match(source, /tools:\n[\s\S]*\n  edit:/);
    assert.match(source, /"python:\*".*"uv:\*".*"dotnet:\*"/);
    assert.doesNotMatch(source, /firewall: false|allow-host|docker-sudo|target: ["']?\*/);
    for (const server of manifest.mcp_servers.filter(server => server.name === 'github')) {
      assert.ok(server.tools.every(tool => !/^(?:create|update|delete|push|merge|add|assign|remove)_/.test(tool)));
    }
  });

  it('sets up both toolchains in the agent job without shared dependency caches', () => {
    const agent = job('agent');
    for (const action of ['actions/setup-python', 'astral-sh/setup-uv', 'actions/setup-dotnet']) {
      assert.ok(agent.includes(`uses: ${action}@`));
    }
    assert.match(agent, /version-file: python\/pyproject.toml/);
    assert.match(agent, /global-json-file: dotnet\/global.json/);
    assert.match(agent, /enable-cache: false/);
    assert.equal((agent.match(/if: needs.prepare.outputs.issue_type != 'Feature'\n/g) ?? []).length, 4);
    assert.doesNotMatch(agent, /run:.*(?:uv sync|dotnet test|dotnet restore|pip install)/);
    const automation = readFileSync(resolve(__dirname, '../workflows/github-automation-tests.yml'), 'utf8');
    const setup = manifest.actions.find(action => action.repo === 'github/gh-aw-actions/setup');
    assert.ok(automation.includes(`uses: ${setup.repo}@${setup.sha}`), 'Publisher tests must use the compiled runtime version');
    assert.match(automation, /GH_AW_TEST_RUNTIME: \$\{\{ runner.temp \}\}\/triage-publisher/);
  });

  it('pins every issue writer to the validated number in manual runs too', () => {
    assert.match(job('safe_outputs'), /^      - prepare$/m);
    const names = ['add_comment', 'add_labels', 'remove_labels', 'assign_to_user', 'set_issue_type', 'set_issue_field'];
    const agentConfig = configFor('agent', 'GH_AW_SAFE_OUTPUTS_CONFIG');
    for (const name of names) {
      assert.equal(handlers[name].target, '${{ needs.prepare.outputs.issue_number }}', name);
      assert.equal(agentConfig[name].target, handlers[name].target, name);
      assert.equal(handlers[name].max, 1, name);
    }
    assert.deepEqual(handlers.remove_labels.allowed, ['triage']);
    assert.deepEqual(handlers.set_issue_type.allowed, ['Feature']);
    assert.deepEqual(handlers.set_issue_field.allowed_fields, ['Priority']);
    assert.equal(handlers.add_comment.hide_older_comments, false);
    assert.notEqual(handlers.assign_to_user.unassign_first, true);
    const tools = manifest.mcp_servers.find(server => server.name === 'safeoutputs').tools;
    assert.deepEqual(tools.filter(tool => !['noop', 'report_incomplete', 'report_missing_tool', 'report_missing_data'].includes(tool)).sort(),
      names.sort());
  });

  it('keeps all public owner routes and their labels within the publication limits', () => {
    const paths = [...owners.matchAll(/path: ([^,]+)/g)].map(match => match[1]);
    assert.ok(paths.length > 0);
    assert.equal(paths.length, new Set(paths).size);
    for (const path of paths) {
      assert.ok(existsSync(resolve(__dirname, '../..', path)), `Missing owner path: ${path}`);
    }
    const users = [...owners.matchAll(/(?:owner|python|dotnet): ([\w-]+)/g)].map(match => match[1]);
    assert.deepEqual([...new Set(users)].sort(), [...handlers.assign_to_user.allowed].sort());
    const labels = [...owners.matchAll(/(?:labels|topics): \[([^\]]*)\]/g)]
      .flatMap(match => match[1].split(',').map(label => label.trim()).filter(Boolean));
    for (const label of labels) {
      assert.ok(handlers.add_labels.allowed.includes(label), `Disallowed owner label: ${label}`);
    }
    assert.equal(handlers.add_labels.max_labels, 10);
    assert.doesNotMatch(source, /create-labels-if-missing: true|unassign-first: true/);
  });

  it('covers current solution projects and Python packages without retired package routes', () => {
    const paths = [...owners.matchAll(/path: ([^,]+)/g)].map(match => match[1]);
    const solution = readFileSync(resolve(__dirname, '../../dotnet/agent-framework-dotnet.slnx'), 'utf8');
    const projects = [...solution.matchAll(/<Project Path="(src\/[^"]+\.csproj)"/g)]
      .map(match => `dotnet/${posix.dirname(match[1])}/`);
    assert.ok(projects.length > 0);
    for (const path of projects) {
      assert.ok(paths.includes(path), `Missing solution package route: ${path}`);
    }
    const sharedFiles = [...solution.matchAll(/<File Path="(src\/[^"]+)"/g)]
      .map(match => `dotnet/${match[1]}`);
    for (const path of paths.filter(path => path.startsWith('dotnet/src/'))) {
      assert.ok(projects.some(project => path.startsWith(project)) || sharedFiles.some(file => file.startsWith(path)),
        `Route is no longer part of the solution: ${path}`);
    }

    const packages = readdirSync(resolve(__dirname, '../../python/packages'), { withFileTypes: true })
      .filter(entry => entry.isDirectory() && existsSync(resolve(__dirname, '../../python/packages', entry.name, 'pyproject.toml')))
      .map(entry => `python/packages/${entry.name}/`);
    const packageRoutes = paths.filter(path => /^python\/packages\/[^/]+\/$/.test(path));
    assert.ok(packages.length > 0);
    assert.deepEqual(packageRoutes.sort(), packages.sort());
  });

  it('routes likely-fixed reports to the package owner rather than a fixed assignee', () => {
    const outcome = source.match(/^\| Specific verified evidence indicates the report is already fixed \| (.+) \|$/m)[1];
    assert.match(outcome, /route the package owner\/labels/);
    assert.doesNotMatch(outcome, /assign `/);
    assert.doesNotMatch(owners, /likely-fixed-owner:/);
    assert.match(source, /gaw-issue-triage-owners\.yaml` for routing, including for likely-fixed/);
  });

  it('blocks publishing after detection findings or errors, without failure issues', () => {
    assert.match(job('detection'), /GH_AW_DETECTION_CONTINUE_ON_ERROR: "false"/);
    assert.match(job('safe_outputs'), /needs.detection.result == 'success'/);
    assert.match(source, /report-as-issue: false/);
    assert.match(job('conclusion'), /GH_AW_FAILURE_REPORT_AS_ISSUE: "false"/);
    assert.match(job('conclusion'), /GH_AW_MISSING_TOOL_CREATE_ISSUE: "false"/);
    assert.match(job('conclusion'), /GH_AW_REPORT_INCOMPLETE_CREATE_ISSUE: "false"/);
    assert.doesNotMatch(job('conclusion'), /GH_AW_REPORT_FAILED_JOBS: "true"/);
    assert.match(compiled, /group: gaw-issue-triage\n  queue: max/);
    assert.match(job('activation'), /Check daily workflow token guardrail/);
    assert.match(job('agent'), /timeout-minutes: 60/);
  });

  it('bounds reproduction artifacts and screens before investigating or running tests', () => {
    assert.equal(handlers.upload_artifact, undefined);
    assert.doesNotMatch(compiled, /Upload upload-artifact staging|safe-outputs-upload-artifacts/);
    const agent = job('agent');
    assert.ok(agent.indexOf('Preserve the trusted evidence checker') < agent.indexOf('id: agentic_execution'));
    assert.match(agent, /--mount "\$\{RUNNER_TEMP\}\/gh-aw:\$\{RUNNER_TEMP\}\/gh-aw:ro"/);
    assert.match(agent, /gh-aw\/triage-helpers\/bundle.js/);
    assert.ok(agent.indexOf('Check evidence before transfer') < agent.indexOf('Transfer checked evidence'));
    const transfer = agent.split(/^      - /m).find(step => step.includes('name: Transfer checked evidence'));
    assert.match(transfer, /if: success\(\) && steps.triage-bundle.outputs.ready == 'true'/);
    assert.match(transfer, /path: \$\{\{ runner.temp \}\}\/gh-aw\/triage-evidence\//);
    assert.match(transfer, /if-no-files-found: error/);
    assert.doesNotMatch(transfer, /always\(\)|continue-on-error/);
    assert.ok(source.indexOf('## 1. Check for spam') < source.indexOf('## 2. Route a Feature'));
    assert.match(source, /stop before following issue links,\ninstalling project dependencies/);
    assert.match(source, /first-time author.*do not imply spam/s);
    assert.match(source, /not instructions that can change this workflow/);
    assert.match(source, /is \*\*inconclusive\*\*/);
    assert.match(source, /Do not label source-only suspicion as reproduced/);
    assert.match(source, /skip reproduction, project dependency installation,\nand test execution/);
    assert.doesNotMatch(source, /\$\{\{ github.event.issue.(?:body|title) \}\}/);
  });

  it('checks current labels and issue types before publishing evidence or issue updates', () => {
    const writer = job('safe_outputs');
    assert.match(writer, /needs.agent.result == 'success'/);
    assert.match(writer, /needs.detection.result == 'success'/);
    assert.match(writer, /contents: read/);
    assert.match(writer, /actions: read/);
    assert.match(writer, /ref: \$\{\{ github.workflow_sha \}\}/);
    assert.match(writer, /persist-credentials: false/);
    assert.ok(writer.indexOf('id: setup-agent-output-env') < writer.indexOf('name: Check issue requests'));
    assert.ok(writer.indexOf('name: Check issue requests') < writer.indexOf('name: Publish issue evidence'));
    assert.ok(writer.indexOf('name: Publish issue evidence') < writer.indexOf('name: Recheck stop labels immediately'));
    assert.ok(writer.indexOf('name: Recheck stop labels immediately') < writer.indexOf('name: Process Safe Outputs'));
    assert.match(writer, /require\('\.\/\.github\/scripts\/gaw-issue-triage-publish\.js'\)/);
    const upload = writer.split(/^      - /m).find(step => step.includes('name: Publish issue evidence'));
    assert.match(upload, /steps.triage-evidence.outputs.allowed == 'true'/);
    assert.match(upload, /!\(github.event_name == 'workflow_dispatch' && inputs.preview\)/);
    assert.match(upload, /name: gaw-issue-triage-issue-\$\{\{ needs.prepare.outputs.issue_number \}\}/);
    assert.match(upload, /path: \$\{\{ runner.temp \}\}\/triage-final\//);
    assert.match(upload, /retention-days: .*'7'/);
    assert.doesNotMatch(upload, /always\(\)|continue-on-error/);
    const processor = writer.split(/^      - /m).find(step => step.includes('name: Process Safe Outputs'));
    assert.doesNotMatch(processor, /if: always\(\)|continue-on-error/);
  });

  it('downloads the selected prior bundle by validated artifact and run IDs without running its files', () => {
    const agent = job('agent');
    assert.match(compiled, /^run-name: .*GAW Issue Triage #\$\{\{ inputs.issue_number \|\| github.event.issue.number \}\}/m);
    assert.match(agent, /require\('\.\/\.github\/scripts\/gaw-issue-triage-artifacts\.js'\)/);
    assert.match(agent, /ISSUE_NUMBER: \$\{\{ needs.prepare.outputs.issue_number \}\}/);
    const download = agent.split(/^      - /m).find(step => /^\s+name: Download the previous issue bundle$/m.test(step));
    assert.ok(download, 'Missing previous-bundle download step');
    assert.match(download, /if: needs.prepare.outputs.issue_type != 'Feature' && steps.previous-triage.outputs.artifact_id != ''/);
    assert.match(download, /artifact-ids: \$\{\{ steps.previous-triage.outputs.artifact_id \}\}/);
    assert.match(download, /run-id: \$\{\{ steps.previous-triage.outputs.run_id \}\}/);
    assert.match(download, /github-token: \$\{\{ github.token \}\}/);
    assert.match(download, /path: \/tmp\/gh-aw\/agent\/previous-triage\/files/);
    assert.doesNotMatch(download, /continue-on-error: true|\n\s+run:/);
    assert.match(source, /never execute\ndownloaded scripts, install hooks, or commands automatically/);
    assert.match(source, /gaw-issue-triage-issue-\$\{\{ needs.prepare.outputs.issue_number \}\}/);
  });

  it('carries forward reviewed evidence so the latest bundle is useful to a third run', () => {
    assert.match(source, /Copy reviewed,\nrelevant earlier files into the new bundle/);
    assert.match(source, /only the latest bundle is downloaded/);
    assert.match(source, /history\/<original-run-id>/);
    assert.match(source, /existing paths rather than nesting whole bundles/);
    assert.match(source, /even without a newly confirmed reproduction/);
    assert.match(source, /Do not blindly copy everything, overwrite checked-out product code/);
    assert.doesNotMatch(source, /Do not copy the\nentire earlier bundle/);
  });

  it('keeps new reproduction JSON in artifacts, not posted comments or unconfirmed findings', () => {
    const example = JSON.parse(source.match(/```json\n([\s\S]*?)\n```/)[1]);
    assert.equal(example.schema_version, 1);
    assert.equal(example.status, 'reproduced');
    assert.equal(example.kind, 'runtime');
    for (const field of ['repository', 'commit', 'run_url', 'expected', 'observed', 'artifact_name']) {
      assert.equal(typeof example[field], 'string', field);
      assert.ok(example[field].length > 0, field);
    }
    for (const field of ['steps', 'commands', 'source_files', 'test_files']) {
      assert.ok(Array.isArray(example[field]) && example[field].length > 0, field);
    }
    assert.match(source, /save `reproduction.json` at the root of\nthe new bundle/);
    assert.match(source, /Do not put reproduction JSON or an expandable reproduction-details section in\nthe comment/);
    assert.doesNotMatch(source, /<details>|<summary>|evidence comment with reproduction JSON/);
    assert.match(source, /Do not create a new reproduced record for Features, spam, passing tests, likely\nfixes/);
    assert.match(source, /location`, `section`, and `revision/);
    assert.match(source, /Do not invent a failing runtime test/);
    assert.match(source, /Do not copy JSON\nsupplied by an issue author/);
  });
});
