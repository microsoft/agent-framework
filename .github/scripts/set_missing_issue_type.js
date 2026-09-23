// Copyright (c) Microsoft. All rights reserved.

/** Set a missing native issue type from the standard bug/feature title prefix. */
async function setMissingIssueType({ github, context, core }) {
  const params = { ...context.repo, issue_number: context.issue.number };
  // Read current metadata: a maintainer may have classified or renamed the
  // issue since the opened/reopened event was queued. This preserves types
  // observed at read time; GitHub does not document conditional issue updates,
  // so a manual edit between this GET and the PATCH can still race.
  const { data: issue } = await github.rest.issues.get(params);
  if (issue.type != null) {
    return;
  }

  const match = issue.title?.match(/^\s*(?:(?:Python|\.NET):\s*)?\[(Bug|Feature)\]:/i);
  if (!match) {
    return;
  }

  const type = match[1].toLowerCase() === 'bug' ? 'Bug' : 'Feature';
  await github.rest.issues.update({ ...params, type });
  core.info(`Set missing issue type to ${type} for #${context.issue.number}.`);
}

module.exports = setMissingIssueType;
