// Copyright (c) Microsoft. All rights reserved.

/**
 * Tests for title_prefix.js.
 *
 * Run with: node --test .github/tests/test_title_prefix.js
 */

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');

const {
  addBracketPrefix,
  addTitlePrefix,
  hasBracketPrefix,
  syncBreakingChangeLabelFromTitle,
  updateTitleForAddedLabel,
} = require('../scripts/title_prefix.js');

function createCore() {
  const messages = [];
  return {
    messages,
    info(message) {
      messages.push(message);
    },
  };
}

function createGithub() {
  const calls = [];
  return {
    calls,
    rest: {
      issues: {
        async addLabels(params) {
          calls.push({ api: 'issues.addLabels', params });
        },
        async update(params) {
          calls.push({ api: 'issues.update', params });
        },
      },
      pulls: {
        async update(params) {
          calls.push({ api: 'pulls.update', params });
        },
      },
    },
  };
}

function createPullRequestContext({ title, labels = [], action = 'labeled', label = 'breaking change' }) {
  return {
    eventName: 'pull_request_target',
    issue: { number: 123 },
    repo: { owner: 'microsoft', repo: 'agent-framework' },
    payload: {
      action,
      label: { name: label },
      pull_request: {
        title,
        labels: labels.map((name) => ({ name })),
      },
    },
  };
}

function createIssueContext({ title, label }) {
  return {
    eventName: 'issues',
    issue: { number: 123 },
    repo: { owner: 'microsoft', repo: 'agent-framework' },
    payload: {
      label: { name: label },
      issue: { title },
    },
  };
}

describe('addBracketPrefix', () => {
  it('prepends the breaking prefix when no title prefix exists', () => {
    assert.equal(addBracketPrefix('Improve docs', '[BREAKING]'), '[BREAKING] Improve docs');
  });

  it('normalizes a case-insensitive leading breaking prefix', () => {
    assert.equal(addBracketPrefix('[breaking] Improve docs', '[BREAKING]'), '[BREAKING] Improve docs');
  });

  it('treats a breaking prefix after a language prefix as already present', () => {
    assert.equal(addBracketPrefix('Python: [breaking] Improve docs', '[BREAKING]'), 'Python: [BREAKING] Improve docs');
    assert.equal(addBracketPrefix('.NET: [Breaking] Improve docs', '[BREAKING]'), '.NET: [BREAKING] Improve docs');
  });

  it('preserves a breaking prefix before a language prefix', () => {
    assert.equal(addBracketPrefix('[Breaking] Python: Improve docs', '[BREAKING]'), '[BREAKING] Python: Improve docs');
    assert.equal(addBracketPrefix('[breaking] .NET: Improve docs', '[BREAKING]'), '[BREAKING] .NET: Improve docs');
  });

  it('moves a later breaking token into the title prefix', () => {
    assert.equal(addBracketPrefix('Python: Improve docs [BREAKING]', '[BREAKING]'), 'Python: [BREAKING] Improve docs');
    assert.equal(
      addBracketPrefix('Docs: explain the [BREAKING] convention', '[BREAKING]'),
      '[BREAKING] Docs: explain the convention',
    );
  });
});

describe('addTitlePrefix', () => {
  it('prepends a language prefix', () => {
    assert.equal(addTitlePrefix('Improve docs', 'Python'), 'Python: Improve docs');
  });

  it('normalizes a language prefix after a breaking prefix without duplicating it', () => {
    assert.equal(addTitlePrefix('[BREAKING] python: Improve docs', 'Python'), '[BREAKING] Python: Improve docs');
  });
});

describe('hasBracketPrefix', () => {
  it('accepts breaking before or after a language prefix', () => {
    assert.equal(hasBracketPrefix('[breaking] Python: Improve docs', '[BREAKING]'), true);
    assert.equal(hasBracketPrefix('Python: [breaking] Improve docs', '[BREAKING]'), true);
    assert.equal(hasBracketPrefix('.NET: [BREAKING] Improve docs', '[BREAKING]'), true);
  });

  it('rejects breaking mentions outside the title prefix', () => {
    assert.equal(hasBracketPrefix('Docs: explain the [BREAKING] convention', '[BREAKING]'), false);
    assert.equal(hasBracketPrefix('Python: Improve docs [BREAKING]', '[BREAKING]'), false);
  });
});

describe('updateTitleForAddedLabel', () => {
  it('updates a PR title when the breaking label is added', async () => {
    const github = createGithub();
    const result = await updateTitleForAddedLabel({
      github,
      context: createPullRequestContext({ title: 'Python: Improve docs' }),
      core: createCore(),
    });

    assert.equal(result.updated, true);
    assert.equal(result.newTitle, 'Python: [BREAKING] Improve docs');
    assert.deepEqual(github.calls, [
      {
        api: 'pulls.update',
        params: {
          pull_number: 123,
          owner: 'microsoft',
          repo: 'agent-framework',
          title: 'Python: [BREAKING] Improve docs',
        },
      },
    ]);
  });

  it('skips no-op title updates', async () => {
    const github = createGithub();
    const result = await updateTitleForAddedLabel({
      github,
      context: createIssueContext({ title: 'Python: [BREAKING] Improve docs', label: 'breaking change' }),
      core: createCore(),
    });

    assert.equal(result.updated, false);
    assert.deepEqual(github.calls, []);
  });
});

describe('syncBreakingChangeLabelFromTitle', () => {
  it('adds the breaking change label when breaking appears after a language prefix', async () => {
    const github = createGithub();
    const result = await syncBreakingChangeLabelFromTitle({
      github,
      context: createPullRequestContext({ title: 'Python: [breaking] Improve docs', labels: ['python'] }),
      core: createCore(),
    });

    assert.equal(result.added, true);
    assert.deepEqual(github.calls, [
      {
        api: 'issues.addLabels',
        params: {
          issue_number: 123,
          owner: 'microsoft',
          repo: 'agent-framework',
          labels: ['breaking change'],
        },
      },
    ]);
  });

  it('does not add the label when breaking is only mentioned later in the title', async () => {
    const github = createGithub();
    const result = await syncBreakingChangeLabelFromTitle({
      github,
      context: createPullRequestContext({ title: 'Docs: explain the [BREAKING] convention' }),
      core: createCore(),
    });

    assert.equal(result.added, false);
    assert.deepEqual(github.calls, []);
  });

  it('skips PRs that already have the breaking change label', async () => {
    const github = createGithub();
    const result = await syncBreakingChangeLabelFromTitle({
      github,
      context: createPullRequestContext({ title: '[BREAKING] Improve docs', labels: ['Breaking Change'] }),
      core: createCore(),
    });

    assert.equal(result.added, false);
    assert.deepEqual(github.calls, []);
  });
});
