// Copyright (c) Microsoft. All rights reserved.

/**
 * Resolve the issue author and check their team membership.
 *
 * @param {object} opts
 * @param {object} opts.github - Octokit REST client from actions/github-script
 * @param {object} opts.context - GitHub Actions context
 * @param {object} opts.core - GitHub Actions core toolkit
 * @param {string} opts.teamSlug - Team slug to check membership against
 * @param {string|number} opts.issueNumber - Issue number to resolve author for
 * @returns {Promise<{author: string|null, isTeamMember: boolean}>}
 */
async function checkTeamMembership({ github, context, core, teamSlug, issueNumber }) {
  let author = context.payload.issue?.user?.login;
  if (!author) {
    const { data: issue } = await github.rest.issues.get({
      owner: context.repo.owner,
      repo: context.repo.repo,
      issue_number: Number(issueNumber),
    });
    author = issue.user?.login;
  }

  if (!author) {
    core.setFailed('Could not determine issue author (user may be deleted).');
    return { author: null, isTeamMember: false };
  }

  try {
    await github.rest.teams.getByName({
      org: context.repo.owner,
      team_slug: teamSlug,
    });
  } catch (error) {
    core.setFailed(`Team lookup failed for ${teamSlug}: ${error.message}`);
    throw error;
  }

  let isTeamMember = false;
  try {
    const teamMembership = await github.rest.teams.getMembershipForUserInOrg({
      org: context.repo.owner,
      team_slug: teamSlug,
      username: author,
    });
    isTeamMember = teamMembership.data.state === 'active';
  } catch (error) {
    if (error.status === 404) {
      core.info(`Author ${author} is not a member of team ${teamSlug}.`);
      isTeamMember = false;
    } else {
      core.setFailed(`Team membership lookup failed for ${author}: ${error.message}`);
      throw error;
    }
  }

  return { author, isTeamMember };
}

module.exports = checkTeamMembership;
