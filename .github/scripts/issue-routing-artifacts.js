// Copyright (c) Microsoft. All rights reserved.

// Search all runs for evidence saved earlier, or only this run for its temporary copy.
// Both read every page of results and ignore unrelated or expired uploads.
async function listMatchingArtifacts({ github, context, name, runId }) {
  const endpoint = runId === undefined
    ? github.rest.actions.listArtifactsForRepo
    : github.rest.actions.listWorkflowRunArtifacts;
  const scope = runId === undefined ? { name } : { run_id: runId };
  const artifacts = await github.paginate(endpoint, {
    ...context.repo, ...scope, per_page: 100,
  });
  return artifacts.filter(artifact => artifact.name === name && !artifact.expired);
}

// Invalid size metadata is an error; each caller applies its own download budget.
function artifactSize(artifact) {
  const size = artifact.size_in_bytes;
  if (!Number.isSafeInteger(size) || size < 1) {
    throw new Error(`Evidence upload ${artifact.id} has an invalid size.`);
  }
  return size;
}

// Before investigation, find the newest usable evidence from an earlier issue run.
async function findEarlierEvidence({ github, context, core, issueNumber }) {
  const number = String(issueNumber);
  if (!/^[1-9][0-9]*$/.test(number) || !Number.isSafeInteger(Number(number))) {
    throw new Error('Issue number must be a positive, safe integer.');
  }

  const name = `issue-routing-issue-${number}`;
  const { data: repository } = await github.rest.repos.get(context.repo);
  const artifacts = await listMatchingArtifacts({ github, context, name });
  artifacts.sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id - a.id);

  // Upload names alone cannot prove which issue or workflow produced the files.
  for (const artifact of artifacts) {
    if (artifact.workflow_run?.repository_id !== repository.id ||
        artifact.workflow_run.id >= context.runId) {
      continue;
    }

    // Earlier evidence must come from a successful default-branch run for this issue,
    // not merely an upload with a familiar name.
    const { data: run } = await github.rest.actions.getWorkflowRun({
      ...context.repo,
      run_id: artifact.workflow_run.id,
    });
    if (run.path !== '.github/workflows/issue-routing.lock.yml' ||
        run.repository.id !== repository.id || run.head_repository?.id !== repository.id ||
        run.head_branch !== repository.default_branch ||
        run.display_title !== `Issue Routing #${number}` ||
        !['workflow_dispatch', 'issues', 'issue_comment'].includes(run.event) ||
        run.status !== 'completed' || run.conclusion !== 'success' ||
        !/^[a-f0-9]{40}$/.test(run.head_sha) ||
        artifact.workflow_run.head_sha !== run.head_sha) {
      core.warning(`Ignoring evidence upload ${artifact.id}: its source run does not match this issue's trusted routing workflow.`);
      continue;
    }

    // ZIP metadata can exceed this budget even when the original files fit.
    if (artifactSize(artifact) > 11 * 1024 * 1024) {
      core.warning(`Ignoring evidence upload ${artifact.id}: it exceeds the 11 MiB download limit.`);
      continue;
    }
    core.info(`Using ${name} from run ${run.id}, commit ${run.head_sha}.`);
    // Supply exact download IDs and source details so old findings stay identifiable.
    return {
      repository: `${context.repo.owner}/${context.repo.repo}`,
      issue_number: Number(number),
      artifact_name: name,
      artifact_id: artifact.id,
      run_id: run.id,
      run_url: run.html_url,
      run_commit: run.head_sha, // Workflow revision; the tested revision is in the report.
      created_at: artifact.created_at,
    };
  }

  core.info(`No evidence saved by an earlier successful run was found for issue #${number}.`);
  return null;
}

// When publishing, get this run's checked evidence, not evidence saved by an earlier run.
async function findThisRunsEvidence({ github, context, core }) {
  if (!Number.isSafeInteger(context.runId) || context.runId < 1) {
    throw new Error('The current workflow run ID must be a positive, safe integer.');
  }
  const [artifact] = await listMatchingArtifacts({
    github, context, name: 'issue-routing-transfer', runId: context.runId,
  });
  if (!artifact) {
    core.info('This run has no checked evidence to publish.');
    return null;
  }
  // Bound the ZIP too, allowing space for the checked file/path metadata.
  if (artifactSize(artifact) > 14 * 1024 * 1024) {
    throw new Error('The evidence copy from the agent job is too large.');
  }
  return artifact.id;
}

module.exports = { findEarlierEvidence, findThisRunsEvidence };
