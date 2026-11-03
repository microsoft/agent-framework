// Copyright (c) Microsoft. All rights reserved.

async function findPreviousTriageArtifact({ github, context, core, issueNumber }) {
  const number = String(issueNumber);
  if (!/^[1-9][0-9]*$/.test(number) || !Number.isSafeInteger(Number(number))) {
    throw new Error('Issue number must be a positive, safe integer.');
  }

  const name = `gaw-issue-triage-issue-${number}`;
  const { data: repository } = await github.rest.repos.get(context.repo);
  const artifacts = await github.paginate(github.rest.actions.listArtifactsForRepo, {
    ...context.repo,
    name,
    per_page: 100,
  });
  artifacts.sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id - a.id);

  // Artifact names alone cannot prove which issue or workflow produced the files.
  for (const artifact of artifacts) {
    if (artifact.name !== name || artifact.expired ||
        artifact.workflow_run?.repository_id !== repository.id ||
        artifact.workflow_run.id >= context.runId) {
      continue;
    }

    const { data: run } = await github.rest.actions.getWorkflowRun({
      ...context.repo,
      run_id: artifact.workflow_run.id,
    });
    if (run.path !== '.github/workflows/gaw-issue-triage.lock.yml' ||
        run.repository.id !== repository.id || run.head_repository?.id !== repository.id ||
        run.head_branch !== repository.default_branch ||
        run.display_title !== `GAW Issue Triage #${number}` ||
        !['workflow_dispatch', 'issues'].includes(run.event) ||
        run.status !== 'completed' || run.conclusion !== 'success' ||
        !/^[a-f0-9]{40}$/.test(run.head_sha) ||
        artifact.workflow_run.head_sha !== run.head_sha) {
      core.warning(`Ignoring artifact ${artifact.id}: its source run does not match this issue's trusted triage workflow.`);
      continue;
    }

    // Allow ZIP overhead above the uploader's 10 MiB limit on original files.
    if (!Number.isSafeInteger(artifact.size_in_bytes) ||
        artifact.size_in_bytes < 1 || artifact.size_in_bytes > 11 * 1024 * 1024) {
      throw new Error(`Triage artifact ${artifact.id} exceeds the download size limit or has an invalid size.`);
    }
    core.info(`Using ${name} from run ${run.id}, commit ${run.head_sha}.`);
    return {
      repository: `${context.repo.owner}/${context.repo.repo}`,
      issue_number: Number(number),
      artifact_name: name,
      artifact_id: artifact.id,
      run_id: run.id,
      run_url: run.html_url,
      run_commit: run.head_sha,
      created_at: artifact.created_at,
    };
  }

  core.info(`No retained bundle from an earlier successful triage run was found for issue #${number}.`);
  return null;
}

module.exports = findPreviousTriageArtifact;
