// Copyright (c) Microsoft. All rights reserved.

// This step only runs when issue updates are allowed and the run is not a preview,
// so a successful result means the run really routed the issue.
const ROUTED_STEP = "Find this run's checked evidence";
const MAX_REPLY_RUNS = 3;
// GitHub returns at most this many runs for a filtered search.
const MAX_SEARCH_RESULTS = 1000;

// Find earlier runs of this workflow that routed the issue, oldest first.
// Runs queue one at a time, so every earlier run has finished by now.
async function findRoutedRuns({ github, context, issue }) {
  let total = 0;
  const runs = await github.paginate(github.rest.actions.listWorkflowRuns, {
    ...context.repo,
    workflow_id: 'issue-routing.lock.yml',
    created: `>=${issue.created_at}`,
    per_page: 100,
  }, response => {
    total = response.data.total_count ?? 0;
    return response.data;
  });
  // Missing runs could hide an earlier routing, so stop rather than guess.
  if (total > MAX_SEARCH_RESULTS) {
    throw new Error(`Too many workflow runs (${total}) since this issue was opened to check its routing history. Run the workflow manually instead.`);
  }
  const candidates = runs
    .filter(run => run.id !== context.runId &&
      run.display_title === `Issue Routing #${issue.number}` &&
      run.status === 'completed')
    .sort((a, b) => a.run_started_at.localeCompare(b.run_started_at));

  const routed = [];
  for (const run of candidates) {
    const jobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun, {
      ...context.repo, run_id: run.id, filter: 'latest', per_page: 100,
    });
    const publish = jobs.find(job => job.name === 'safe_outputs' && job.conclusion === 'success');
    if (publish?.steps?.some(step => step.name === ROUTED_STEP && step.conclusion === 'success')) {
      routed.push(run);
    }
  }
  return routed;
}

// Decide whether an automatic run should go ahead, given earlier routed runs.
// Returns a reason to skip, or an empty string to continue.
async function automaticSkipReason({ github, context, issue }) {
  const routed = await findRoutedRuns({ github, context, issue });

  // New issues and type changes are routed only once.
  if (context.eventName !== 'issue_comment') {
    return routed.length ? `issue was already routed by run ${routed.at(-1).id}.` : '';
  }

  // A reporter reply re-runs routing only if no routed run has seen it yet,
  // with a small cap so replies cannot trigger runs indefinitely.
  const repliedAt = context.payload.comment?.created_at;
  if (!repliedAt) {
    throw new Error('The comment event has no creation time.');
  }
  if (routed.some(run => run.run_started_at >= repliedAt)) {
    return 'a later routing run already included this reply.';
  }
  const replyRuns = routed.filter(run => run.event === 'issue_comment').length;
  if (replyRuns >= MAX_REPLY_RUNS) {
    return `the limit of ${MAX_REPLY_RUNS} reply re-runs was reached.`;
  }
  return '';
}

module.exports = { findRoutedRuns, automaticSkipReason, ROUTED_STEP, MAX_REPLY_RUNS };
