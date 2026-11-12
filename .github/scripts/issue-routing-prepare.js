// Copyright (c) Microsoft. All rights reserved.

const checkTeamMembership = require('./check_team_membership.js');
const { stopReason } = require('./issue-routing-publish.js');
const { automaticSkipReason } = require('./issue-routing-history.js');

// `github` uses the App token for issue and team reads. `actionsGithub` uses the
// workflow token, which can read this repository's earlier workflow runs.
async function prepareIssueRouting({ github, actionsGithub, context, core, issueNumber = '', teamSlug = '' }) {
  // Keep the agent disabled unless every required check below passes.
  core.setOutput('should_route', 'false');

  // Manual runs take an explicit issue number; automatic runs come from issue
  // events or a reporter's reply comment.
  const manual = context.eventName === 'workflow_dispatch';
  const reply = context.eventName === 'issue_comment';
  if (!manual && !reply && context.eventName !== 'issues') {
    throw new Error('Issue routing requires an issue event, a reply comment, or manual dispatch.');
  }

  // Validate the number before making API calls or passing it to later jobs.
  const input = String(manual ? issueNumber : context.payload.issue?.number ?? '');
  if (!/^[1-9][0-9]*$/.test(input) || !Number.isSafeInteger(Number(input))) {
    throw new Error('Issue number must be a positive, safe integer.');
  }

  // Fetch current details rather than relying on a possibly outdated event payload.
  // GitHub's issues API also returns pull requests, which must not enter routing.
  const { data: issue } = await github.rest.issues.get({
    ...context.repo,
    issue_number: Number(input),
  });
  if (issue.pull_request || issue.number !== Number(input)) {
    throw new Error('The selected number must identify an issue, not a pull request.');
  }

  // Export validated metadata. Only automatic runs are limited to Bugs and Features.
  core.setOutput('issue_number', input);
  const issueType = issue.type?.name ?? '';
  core.setOutput('issue_type', issueType);
  if (!manual && !['Bug', 'Feature'].includes(issueType)) {
    core.info('Skipping automatic routing: the issue is not a Bug or Feature.');
    return;
  }

  // Respect maintainer stop labels even for manual runs. An allow label can release
  // a review hold, but cannot override a spam or suspected-spam label.
  const reason = stopReason(issue);
  if (reason) {
    core.info(`Skipping routing: ${reason}`);
    return;
  }

  // Skip developer-team authors on automatic runs, checking the fetched author
  // rather than the event actor. Manual runs bypass this check; lookup errors stop the run.
  if (!manual) {
    if (!teamSlug.trim() || !issue.user?.login) {
      throw new Error('The developer team and current issue author are required for automatic routing.');
    }
    const { isTeamMember } = await checkTeamMembership({
      github,
      context,
      core,
      teamSlug: teamSlug.trim(),
      issueNumber: input,
      username: issue.user.login,
    });
    if (isTeamMember) {
      core.info('Skipping automatic routing: the issue author belongs to the developer team.');
      return;
    }

    // Reply re-runs need a reply from the original reporter while details were
    // requested. Recheck the fetched issue rather than trusting the event payload.
    if (reply) {
      const labels = (issue.labels ?? []).map(label => typeof label === 'string' ? label : label?.name);
      if (context.payload.comment?.user?.login !== issue.user.login || !labels.includes('requested-info')) {
        core.info('Skipping automatic routing: the comment is not a reporter reply to a request for details.');
        return;
      }
    }

    // Avoid routing the same issue twice.
    if (!actionsGithub) {
      throw new Error('A workflow-run reader is required for automatic routing.');
    }
    const skip = await automaticSkipReason({ github: actionsGithub, context, issue });
    if (skip) {
      core.info(`Skipping automatic routing: ${skip}`);
      return;
    }
  }

  // Let the agent run only after input, label, and applicable author checks succeed.
  core.setOutput('should_route', 'true');
}

module.exports = prepareIssueRouting;
