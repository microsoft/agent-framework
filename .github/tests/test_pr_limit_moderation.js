// Copyright (c) Microsoft. All rights reserved.

/**
 * Tests for pr_limit_moderation.js.
 *
 * Run with: node --test .github/tests/test_pr_limit_moderation.js
 */

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');

const { enforcePrLimit } = require('../scripts/pr_limit_moderation.js');


// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createContext({ author = 'community-user', labels = [], number = 123 } = {}) {
  return {
    repo: {
      owner: 'microsoft',
      repo: 'agent-framework',
    },
    payload: {
      pull_request: {
        number,
        labels: labels.map((name) => ({ name })),
        user: {
          login: author,
        },
      },
    },
  };
}

function createCore() {
  const messages = [];
  return {
    messages,
    info(message) {
      messages.push(message);
    },
  };
}

function createGithub({ totalCount, itemNumbers, labelExists = true }) {
  const calls = [];

  return {
    calls,
    rest: {
      search: {
        async issuesAndPullRequests(params) {
          calls.push({ api: 'search.issuesAndPullRequests', params });
          return {
            data: {
              total_count: totalCount,
              items: itemNumbers.map((number) => ({ number })),
            },
          };
        },
      },
      issues: {
        async getLabel(params) {
          calls.push({ api: 'issues.getLabel', params });
          if (!labelExists) {
            const error = new Error('Not Found');
            error.status = 404;
            throw error;
          }
          return { data: { name: params.name } };
        },
        async createLabel(params) {
          calls.push({ api: 'issues.createLabel', params });
          return { data: { name: params.name } };
        },
        async addLabels(params) {
          calls.push({ api: 'issues.addLabels', params });
          return { data: [] };
        },
        async createComment(params) {
          calls.push({ api: 'issues.createComment', params });
          return { data: { id: 1 } };
        },
      },
      pulls: {
        async update(params) {
          calls.push({ api: 'pulls.update', params });
          return { data: { state: params.state } };
        },
      },
    },
  };
}


// ---------------------------------------------------------------------------
// PR limit enforcement
// ---------------------------------------------------------------------------

describe('PR limit enforcement', () => {
  it('does not close the PR when the author is at the open PR limit', async () => {
    const github = createGithub({
      totalCount: 10,
      itemNumbers: [1, 2, 3, 4, 5, 6, 7, 8, 9, 123],
    });

    const result = await enforcePrLimit({
      github,
      context: createContext(),
      core: createCore(),
      exemptLabelName: 'pr-limit-exempt',
      maxOpenPrs: 10,
      labelName: 'too-many-prs',
    });

    assert.equal(result.closed, false);
    assert.equal(result.openPrCount, 10);
    assert.deepEqual(
      github.calls.map((call) => call.api),
      ['search.issuesAndPullRequests'],
    );
  });

  it('counts the new PR when search has not indexed it yet', async () => {
    const github = createGithub({
      totalCount: 10,
      itemNumbers: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    });

    const result = await enforcePrLimit({
      github,
      context: createContext(),
      core: createCore(),
      exemptLabelName: 'pr-limit-exempt',
      maxOpenPrs: 10,
      labelName: 'too-many-prs',
    });

    assert.equal(result.closed, true);
    assert.equal(result.openPrCount, 11);
    assert.deepEqual(
      github.calls.map((call) => call.api),
      [
        'search.issuesAndPullRequests',
        'issues.getLabel',
        'issues.addLabels',
        'issues.createComment',
        'pulls.update',
      ],
    );
  });

  it('creates the label when it does not already exist', async () => {
    const github = createGithub({
      totalCount: 11,
      itemNumbers: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 123],
      labelExists: false,
    });

    const result = await enforcePrLimit({
      github,
      context: createContext(),
      core: createCore(),
      exemptLabelName: 'pr-limit-exempt',
      maxOpenPrs: 10,
      labelName: 'too-many-prs',
    });

    assert.equal(result.closed, true);
    assert.deepEqual(
      github.calls.map((call) => call.api),
      [
        'search.issuesAndPullRequests',
        'issues.getLabel',
        'issues.createLabel',
        'issues.addLabels',
        'issues.createComment',
        'pulls.update',
      ],
    );
    assert.equal(
      github.calls.find((call) => call.api === 'issues.createLabel').params.name,
      'too-many-prs',
    );
  });

  it('tolerates a 422 race when creating the label', async () => {
    const github = createGithub({
      totalCount: 11,
      itemNumbers: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 123],
      labelExists: false,
    });
    github.rest.issues.createLabel = async (params) => {
      github.calls.push({ api: 'issues.createLabel', params });
      const error = new Error('Validation Failed');
      error.status = 422;
      throw error;
    };

    const result = await enforcePrLimit({
      github,
      context: createContext(),
      core: createCore(),
      exemptLabelName: 'pr-limit-exempt',
      maxOpenPrs: 10,
      labelName: 'too-many-prs',
    });

    assert.equal(result.closed, true);
    assert.deepEqual(
      github.calls.map((call) => call.api),
      [
        'search.issuesAndPullRequests',
        'issues.getLabel',
        'issues.createLabel',
        'issues.addLabels',
        'issues.createComment',
        'pulls.update',
      ],
    );
  });

  it('uses a diplomatic close message with the configured limit', async () => {
    const github = createGithub({
      totalCount: 11,
      itemNumbers: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 123],
    });

    await enforcePrLimit({
      github,
      context: createContext({ author: 'octo-contributor' }),
      core: createCore(),
      exemptLabelName: 'pr-limit-exempt',
      maxOpenPrs: 10,
      labelName: 'too-many-prs',
    });

    const comment = github.calls.find((call) => call.api === 'issues.createComment').params.body;
    assert.match(comment, /Thank you for your contribution/);
    assert.match(comment, /limit community contributors to 10 open pull requests/);
    assert.match(comment, /@octo-contributor/);
    assert.match(comment, /`pr-limit-exempt` label and reopen/);
  });

  it('does not close an exempt PR when it is reopened', async () => {
    const github = createGithub({
      totalCount: 11,
      itemNumbers: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 123],
    });

    const result = await enforcePrLimit({
      github,
      context: createContext({ labels: ['PR-LIMIT-EXEMPT'] }),
      core: createCore(),
      exemptLabelName: 'pr-limit-exempt',
      maxOpenPrs: 10,
      labelName: 'too-many-prs',
    });

    assert.equal(result.closed, false);
    assert.equal(result.exempt, true);
    assert.equal(result.openPrCount, null);
    assert.deepEqual(github.calls, []);
  });

  it('does not over-count when the current PR is not on the first search page', async () => {
    const github = createGithub({
      totalCount: 101,
      itemNumbers: Array.from({ length: 100 }, (_, index) => index + 1),
    });

    const result = await enforcePrLimit({
      github,
      context: createContext({ number: 123 }),
      core: createCore(),
      exemptLabelName: 'pr-limit-exempt',
      maxOpenPrs: 10,
      labelName: 'too-many-prs',
    });

    assert.equal(result.closed, true);
    assert.equal(result.openPrCount, 101);
  });
});
