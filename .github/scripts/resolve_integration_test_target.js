// Copyright (c) Microsoft. All rights reserved.

const DECISIVE_REVIEW_STATES = new Set(['APPROVED', 'CHANGES_REQUESTED', 'DISMISSED']);
const SHA_PATTERN = /^[0-9a-f]{40}$/;
const BRANCH_PATTERN = /^[a-zA-Z0-9_./-]+$/;

function assertValidSha(sha, description) {
  if (!SHA_PATTERN.test(sha)) {
    throw new Error(`GitHub returned an invalid ${description} SHA.`);
  }
}

function hasWritePermission(permissionData) {
  return permissionData.user?.permissions?.push === true
    || ['admin', 'maintain', 'write'].includes(permissionData.permission);
}

function latestDecisiveReviews(reviews) {
  const latestByReviewer = new Map();
  const sortedReviews = [...reviews].sort((left, right) => {
    const submittedComparison = (left.submitted_at || '').localeCompare(right.submitted_at || '');
    return submittedComparison || Number(left.id) - Number(right.id);
  });

  for (const review of sortedReviews) {
    const state = review.state?.toUpperCase();
    const reviewer = review.user?.login?.toLowerCase();
    if (reviewer && DECISIVE_REVIEW_STATES.has(state)) {
      latestByReviewer.set(reviewer, review);
    }
  }

  return latestByReviewer;
}

async function resolvePullRequest({ github, context, core, prNumber, requiredApprovals }) {
  if (!/^[0-9]+$/.test(prNumber)) {
    throw new Error('Invalid PR number. Only numeric values are allowed.');
  }

  const pullNumber = Number(prNumber);
  const { data: pullRequest } = await github.rest.pulls.get({
    ...context.repo,
    pull_number: pullNumber,
  });

  if (pullRequest.state !== 'open') {
    throw new Error(`PR #${pullNumber} is not open (state: ${pullRequest.state}).`);
  }

  const headSha = pullRequest.head.sha;
  const baseSha = pullRequest.base.sha;
  assertValidSha(headSha, 'PR head');
  assertValidSha(baseSha, 'PR base');

  const reviews = await github.paginate(github.rest.pulls.listReviews, {
    ...context.repo,
    pull_number: pullNumber,
    per_page: 100,
  });
  const latestReviews = latestDecisiveReviews(reviews);
  const author = pullRequest.user?.login?.toLowerCase();
  const approvalCandidates = [...latestReviews.entries()]
    .filter(([, review]) => review.state.toUpperCase() === 'APPROVED')
    .filter(([, review]) => review.commit_id === headSha)
    .filter(([reviewer]) => reviewer !== author);

  const approvedMaintainers = [];
  for (const [reviewer] of approvalCandidates) {
    const { data: permissionData } = await github.rest.repos.getCollaboratorPermissionLevel({
      ...context.repo,
      username: reviewer,
    });
    if (hasWritePermission(permissionData)) {
      approvedMaintainers.push(reviewer);
    } else {
      core.info(`Ignoring approval from ${reviewer}: reviewer does not have write permission.`);
    }
  }

  if (approvedMaintainers.length < requiredApprovals) {
    throw new Error(
      `PR #${pullNumber} head ${headSha} requires ${requiredApprovals} approvals from unique `
      + `write-capable maintainers; found ${approvedMaintainers.length}.`,
    );
  }

  core.info(
    `PR #${pullNumber} head ${headSha} approved by: ${approvedMaintainers.join(', ')}.`,
  );
  return {
    baseRef: baseSha,
    checkoutRef: headSha,
    description: `PR #${pullNumber}`,
  };
}

async function resolveBranch({ github, context, core, branch }) {
  if (!BRANCH_PATTERN.test(branch)) {
    throw new Error(
      'Invalid branch name. Only alphanumeric characters, hyphens, underscores, dots, and slashes '
      + 'are allowed.',
    );
  }

  const [{ data: repository }, { data: targetBranch }] = await Promise.all([
    github.rest.repos.get(context.repo),
    github.rest.repos.getBranch({ ...context.repo, branch }),
  ]);
  const { data: baseBranch } = await github.rest.repos.getBranch({
    ...context.repo,
    branch: repository.default_branch,
  });

  const checkoutRef = targetBranch.commit.sha;
  const baseRef = baseBranch.commit.sha;
  assertValidSha(checkoutRef, 'branch head');
  assertValidSha(baseRef, 'default branch');
  core.info(`Branch ${branch} resolved to immutable commit ${checkoutRef}.`);

  return {
    baseRef,
    checkoutRef,
    description: `branch ${branch}`,
  };
}

/**
 * Resolve a manually requested integration-test target to an immutable commit.
 *
 * Pull requests must have fresh approvals from two unique write-capable
 * maintainers for the exact head commit. Branches are limited to branches in
 * the base repository and are pinned to their current commit.
 */
async function resolveIntegrationTestTarget({
  github,
  context,
  core,
  prNumber = '',
  branch = '',
  requiredApprovals = 2,
}) {
  const normalizedPrNumber = prNumber.trim();
  const normalizedBranch = branch.trim();

  if (normalizedPrNumber && normalizedBranch) {
    throw new Error('Please provide either a PR number or a branch name, not both.');
  }
  if (!normalizedPrNumber && !normalizedBranch) {
    throw new Error('Please provide either a PR number or a branch name.');
  }

  if (normalizedPrNumber) {
    return resolvePullRequest({
      github,
      context,
      core,
      prNumber: normalizedPrNumber,
      requiredApprovals,
    });
  }
  return resolveBranch({
    github,
    context,
    core,
    branch: normalizedBranch,
  });
}

module.exports = resolveIntegrationTestTarget;
