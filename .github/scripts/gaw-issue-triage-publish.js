// Copyright (c) Microsoft. All rights reserved.

const fs = require('node:fs');

// Share the same label rules before investigation and before publication.
// An allow label can release a review hold, but cannot override a deny label.
function stopReason(issue) {
  const labels = new Set((issue.labels ?? []).map(label =>
    (typeof label === 'string' ? label : label.name).toLowerCase()));
  if (labels.has('spam') || labels.has('suspected-spam')) {
    return 'a manual deny label is present.';
  }
  if (labels.has('needs-maintainer-triage') && !labels.has('safe-to-triage')) {
    return 'maintainer review is required. Review the report before adding safe-to-triage.';
  }
  return '';
}

// Check the whole batch before any writer runs, rather than discovering a forbidden
// type change after earlier requests have already updated the issue.
function validateRequests(output) {
  if (!Array.isArray(output.items)) {
    throw new Error('Triage publication requires an items array.');
  }
  for (const item of output.items) {
    if (!item || typeof item.type !== 'string') {
      throw new Error('Invalid triage publication request.');
    }
    if (item.type === 'set_issue_type' && item.issue_type !== 'Feature') {
      throw new Error('Triage may only set the issue type to Feature; clearing it is not allowed.');
    }
  }
}

// Called before evidence uploads and issue updates. This helper does not write to
// GitHub; it permits publication or replaces queued requests with a logged no-op.
async function checkPublication({ github, context, core, issueNumber, outputPath }) {
  // Errors must leave publication disabled, not fall back to allowing updates.
  core.setOutput('allowed', 'false');
  if (!/^[1-9][0-9]*$/.test(String(issueNumber)) || !Number.isSafeInteger(Number(issueNumber))) {
    throw new Error('Issue number must be a positive, safe integer.');
  }
  // Inspect the same request file that the built-in publisher will consume.
  const output = JSON.parse(fs.readFileSync(outputPath, 'utf8'));
  validateRequests(output);
  // Preparation may have happened an hour ago; respect labels added since then.
  const { data: issue } = await github.rest.issues.get({
    ...context.repo, issue_number: Number(issueNumber),
  });
  if (issue.pull_request || issue.number !== Number(issueNumber)) {
    throw new Error('The selected number must identify an issue, not a pull request.');
  }
  const reason = stopReason(issue);
  if (reason) {
    core.notice(`Skipping triage publication: ${reason}`);
    // Keep an explicit no-op for the publisher instead of leaving an ambiguous empty result.
    output.items = [{ type: 'noop', reason: `Publication stopped: ${reason}` }];
    fs.writeFileSync(outputPath, JSON.stringify(output));
    return;
  }
  core.setOutput('allowed', 'true');
}

module.exports = { stopReason, validateRequests, checkPublication };
