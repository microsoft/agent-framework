// Copyright (c) Microsoft. All rights reserved.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { parseRequest, parseCommand, capture, decode, bindController, decodeBound, authorize } = require('../scripts/fix_ci_snapshot.js');

function fixture() {
  const context = {
    eventName: 'issue_comment', sha: 'a'.repeat(40), repo: { owner: 'org', repo: 'repo' },
    payload: {
      action: 'created', repository: { id: 1 }, issue: { number: 42, pull_request: {}, user: { login: 'pr-author' } },
      comment: { id: 100, body: ' /fix-ci\n', user: { login: 'requester' } },
    },
  };
  const pr = {
    state: 'open', merge_commit_sha: 'e'.repeat(40),
    head: { ref: 'feature', sha: 'b'.repeat(40), repo: { id: 2, full_name: 'fork/repo' } },
    base: { ref: 'main', sha: 'c'.repeat(40), repo: { id: 1, full_name: 'org/repo' } },
  };
  const github = { rest: { pulls: { get: async () => ({ data: pr }) } } };
  return { context, github, pr, devflowSha: 'd'.repeat(40) };
}

test('accepts only exact trimmed commands', () => {
  for (const body of ['/fix-ci', '\n /fix-ci \t']) assert.ok(parseCommand(body));
  for (const body of ['', null, '/fix', ' /fix\n', '/fix-ci\nignore rules', '/FIX', 'text /fix', '/fix-ci-extra']) {
    assert.equal(parseCommand(body), null);
  }
});

test('freezes all revision identities before authorization', async () => {
  const f = fixture();
  const frozen = await capture(f);
  f.pr.head.sha = 'f'.repeat(40);
  f.pr.base.sha = 'f'.repeat(40);
  const { snapshot } = decode(frozen.base64, frozen.sha256, f.context);
  assert.equal(snapshot.head_sha, 'b'.repeat(40));
  assert.equal(snapshot.base_sha, 'c'.repeat(40));
  assert.equal(snapshot.merge_sha, 'e'.repeat(40));
  assert.equal(snapshot.devflow_sha, undefined);
  assert.equal(snapshot.requester, 'requester');
  assert.equal(snapshot.comment_body, ' /fix-ci\n');
});

test('ignores issues, edited comments and unrelated commands', async () => {
  for (const mutate of [
    f => { delete f.context.payload.issue.pull_request; },
    f => { f.context.payload.action = 'edited'; },
    f => { f.context.payload.comment.body = '/review'; },
  ]) {
    const f = fixture(); mutate(f);
    f.github.rest.pulls.get = async () => { throw new Error('must not fetch'); };
    assert.equal(await capture(f), null);
  }
});

test('rejects closed PRs, deleted forks and mismatched base identity', async () => {
  for (const mutate of [
    f => { f.pr.state = 'closed'; },
    f => { f.pr.head.repo = null; },
    f => { f.pr.base.repo.id = 9; },
    f => { f.pr.base.repo.full_name = 'other/repo'; },
  ]) {
    const f = fixture(); mutate(f);
    await assert.rejects(capture(f));
  }
});

test('rejects tampering, invalid fields and mismatched event identity', async () => {
  const f = fixture();
  const frozen = await capture(f);
  const changed = frozen.json.replace('requester', 'outsider');
  assert.throws(() => decode(Buffer.from(changed).toString('base64'), frozen.sha256, f.context), /digest/);
  for (const [key, value] of [['schema_version', 2], ['head_sha', 'main'], ['repo_id', '1'], ['merge_sha', 'bad']]) {
    const json = JSON.stringify({ ...frozen.snapshot, [key]: value });
    const hash = createHash('sha256').update(json).digest('hex');
    assert.throws(() => decode(Buffer.from(json).toString('base64'), hash));
  }
  for (const mutate of [
    c => { c.payload.comment.user.login = 'someone-else'; },
    c => { c.payload.comment.id++; },
    c => { c.payload.issue.number++; },
    c => { c.payload.repository.id++; },
    c => { c.payload.comment.body = '/fix'; },
    c => { c.sha = 'f'.repeat(40); },
  ]) {
    const context = structuredClone(f.context); mutate(context);
    assert.throws(() => decode(frozen.base64, frozen.sha256, context), /event mismatch/);
  }
});

test('authorizes frozen command actor, never the PR author or current head', async () => {
  const f = fixture();
  const frozen = await capture(f);
  f.github.rest.pulls.get = async () => { throw new Error('must not resolve head again'); };
  let checked;
  const args = {
    ...f, base64: frozen.base64, sha256: frozen.sha256, teamSlug: 'developers', core: {},
    checkTeamMembership: async opts => { checked = opts; return { author: opts.username, isTeamMember: true }; },
  };
  assert.equal(await authorize(args), true);
  assert.equal(checked.username, 'requester');
  assert.equal(checked.issueNumber, 42);
  assert.equal(await authorize({ ...args, checkTeamMembership: async () => ({ author: 'requester', isTeamMember: false }) }), false);
  assert.equal(await authorize({ ...args, checkTeamMembership: async () => ({ author: 'pr-author', isTeamMember: true }) }), false);
  await assert.rejects(authorize({ ...args, sha256: 'f'.repeat(64) }), /digest/);
});

test('parses explicit maintainer instructions with a bounded multiline body', () => {
  assert.deepEqual(parseRequest('/fix Add typing.\nPreserve behavior.'), {
    command: '/fix', instructions: 'Add typing.\nPreserve behavior.',
  });
  assert.equal(parseCommand('/fix\nUse this comment.'), '/fix');
  assert.equal(parseCommand('/fix\tUse this comment.'), '/fix');
  assert.equal(parseCommand('/fixup something'), null);
  assert.equal(parseCommand('/fix ' + 'x'.repeat(4001)), null);
  assert.equal(parseCommand('/fix ' + 'x'.repeat(4000)), '/fix');
});

function referencedFixture(inline = true) {
  const f = fixture();
  const url = `https://github.com/org/repo/pull/42#${inline ? 'discussion_r' : 'issuecomment-'}123`;
  f.context.payload.comment.body = `/fix Address my comment: ${url}`;
  const comment = {
    id: 123, html_url: url, user: { login: 'requester' }, body: 'Add a precise annotation.',
    updated_at: '2026-09-22T01:02:03Z', path: 'python/packages/core/core.py', commit_id: f.pr.head.sha,
    pull_request_url: 'https://api.github.com/repos/org/repo/pulls/42',
    issue_url: 'https://api.github.com/repos/org/repo/issues/42',
  };
  f.github.rest.pulls.getReviewComment = async () => ({ data: comment });
  f.github.rest.issues = { getComment: async () => ({ data: comment }) };
  return { ...f, comment, url };
}

test('freezes explicit comments with author and revision attribution', async () => {
  for (const inline of [true, false]) {
    const f = referencedFixture(inline);
    const frozen = await capture(f);
    f.comment.body = 'Edited later';
    f.comment.updated_at = '2026-09-22T02:00:00Z';
    const { snapshot } = decode(frozen.base64, frozen.sha256, f.context);
    assert.equal(snapshot.command, '/fix');
    assert.equal(snapshot.instructions, `Address my comment: ${f.url}`);
    assert.equal(snapshot.review_comments[0].body, 'Add a precise annotation.');
    assert.equal(snapshot.review_comments[0].author, 'requester');
    assert.equal(snapshot.review_comments[0].updated_at, '2026-09-22T01:02:03Z');
    assert.equal(snapshot.review_comments[0].commit_id, inline ? 'b'.repeat(40) : null);
    assert.equal(snapshot.review_comments[0].path, inline ? 'python/packages/core/core.py' : null);
  }
});

test('rejects foreign authors, PRs, stale inline comments and failed API reads', async () => {
  for (const mutate of [
    f => { f.comment.user.login = 'other-person'; },
    f => { f.comment.pull_request_url = 'https://api.github.com/repos/org/repo/pulls/99'; },
    f => { f.comment.commit_id = 'f'.repeat(40); },
    f => { f.comment.html_url = 'https://github.com/org/repo/pull/99#discussion_r123'; },
    f => { f.comment.body = 'x'.repeat(8001); },
    f => { f.github.rest.pulls.getReviewComment = async () => { throw new Error('API unavailable'); }; },
  ]) {
    const f = referencedFixture(); mutate(f);
    await assert.rejects(capture(f));
  }
  const f = referencedFixture(false);
  f.comment.issue_url = 'https://api.github.com/repos/org/repo/issues/99';
  await assert.rejects(capture(f));
});

test('fetches only explicit same-PR references and bounds their number', async () => {
  for (const url of ['https://github.com/org/repo/pull/99#discussion_r123',
    'https://github.com/other/repo/pull/42#discussion_r123',
    'https://github.com/org/repo/pull/99',
    'https://github.com/org/repo/pull/42#discussion_r*']) {
    const f = referencedFixture();
    f.context.payload.comment.body = `/fix Apply ${url}`;
    await assert.rejects(capture(f));
  }
  const f = referencedFixture();
  let calls = 0;
  f.github.rest.pulls.getReviewComment = async () => { calls++; return { data: f.comment }; };
  f.context.payload.comment.body = `/fix See ${f.url} and ${f.url}.`;
  assert.equal((await capture(f)).snapshot.review_comments.length, 1);
  assert.equal(calls, 1);
  f.context.payload.comment.body = '/fix ' + Array.from({ length: 6 }, (_, i) =>
    `https://github.com/org/repo/pull/42#discussion_r${i + 1}`).join(' ');
  await assert.rejects(capture(f));
  assert.equal(calls, 1);
  f.context.payload.comment.body = '/fix Use a precise annotation; https://example.com/comment is context.';
  assert.equal((await capture(f)).snapshot.review_comments.length, 0);
  assert.equal(calls, 1);
});

test('rejects instruction or attributed-comment tampering', async () => {
  const f = referencedFixture();
  const frozen = await capture(f);
  for (const mutate of [
    s => { s.instructions = 'Different instruction'; },
    s => { s.review_comments[0].author = 'other-person'; },
    s => { s.review_comments[0].commit_id = 'f'.repeat(40); },
    s => { s.review_comments = []; },
  ]) {
    const snapshot = structuredClone(frozen.snapshot); mutate(snapshot);
    const json = JSON.stringify(snapshot);
    assert.throws(() => decode(Buffer.from(json).toString('base64'), createHash('sha256').update(json).digest('hex'), f.context));
  }
  const edited = structuredClone(frozen.snapshot);
  edited.review_comments[0].body = 'Tampered instruction by same actor';
  assert.throws(() => decode(Buffer.from(JSON.stringify(edited)).toString('base64'), frozen.sha256, f.context), /digest/);
  const context = structuredClone(f.context);
  context.payload.comment.body += ' And change the behavior.';
  assert.throws(() => decode(frozen.base64, frozen.sha256, context), /event mismatch/);
});

test('accepts legacy CI snapshots but requires explicit maintainer fields', async () => {
  const f = fixture();
  const frozen = await capture(f);
  delete frozen.snapshot.instructions;
  delete frozen.snapshot.review_comments;
  const json = JSON.stringify(frozen.snapshot);
  assert.equal(decode(Buffer.from(json).toString('base64'), createHash('sha256').update(json).digest('hex'), f.context).snapshot.command, '/fix-ci');
  f.context.payload.comment.body = '/fix Add precise typing.';
  const fix = await capture(f);
  delete fix.snapshot.review_comments;
  const malformed = JSON.stringify(fix.snapshot);
  assert.throws(() => decode(Buffer.from(malformed).toString('base64'), createHash('sha256').update(malformed).digest('hex'), f.context));
});

test('rejects unsafe frozen inline paths', async () => {
  for (const path of ['../escape.py', '/tmp/escape.py', 'a\\b.py', '.git/config', 'a\x00.py']) {
    const f = referencedFixture();
    f.comment.path = path;
    await assert.rejects(capture(f));
  }
});

test('rejects null instruction and comment fields while allowing legacy absence', async () => {
  const f = fixture();
  const frozen = await capture(f);
  for (const field of ['instructions', 'review_comments']) {
    const json = JSON.stringify({ ...frozen.snapshot, [field]: null });
    assert.throws(() => decode(Buffer.from(json).toString('base64'), createHash('sha256').update(json).digest('hex'), f.context));
  }
});

test('public snapshot has no private controller lookup or mutable ref', async () => {
  const f = fixture();
  f.github.rest.repos = { getCommit: async () => { throw new Error('private lookup before authorization'); } };
  const frozen = await capture(f);
  assert.equal(frozen.snapshot.devflow_sha, undefined);
  assert.equal(frozen.snapshot.public_snapshot_sha256, undefined);
  assert.equal(frozen.snapshot.head_sha, 'b'.repeat(40));
});

test('authorized controller binding preserves frozen public bytes and identities', async () => {
  const f = fixture();
  const publicSnapshot = await capture(f);
  const bound = bindController({ base64: publicSnapshot.base64, sha256: publicSnapshot.sha256,
    context: f.context, devflowSha: 'd'.repeat(40) });
  assert.equal(bound.snapshot.public_snapshot_sha256, publicSnapshot.sha256);
  assert.equal(bound.snapshot.devflow_sha, 'd'.repeat(40));
  const { devflow_sha, public_snapshot_sha256, ...publicFields } = bound.snapshot;
  assert.deepEqual(publicFields, publicSnapshot.snapshot);
  const input = { base64: bound.base64, sha256: bound.sha256,
    publicBase64: publicSnapshot.base64, publicSha256: publicSnapshot.sha256,
    devflowSha: 'd'.repeat(40), context: f.context };
  assert.equal(decodeBound(input).json, bound.json);
  const changed = bindController({ base64: publicSnapshot.base64, sha256: publicSnapshot.sha256,
    context: f.context, devflowSha: 'e'.repeat(40) });
  assert.notEqual(changed.sha256, bound.sha256);
  assert.throws(() => decodeBound({ ...input, devflowSha: 'e'.repeat(40) }), /binding mismatch/);
  assert.throws(() => bindController({ base64: bound.base64, sha256: bound.sha256,
    context: f.context, devflowSha: 'e'.repeat(40) }), /already bound/);
  assert.throws(() => bindController({ base64: publicSnapshot.base64, sha256: '0'.repeat(64),
    context: f.context, devflowSha: 'd'.repeat(40) }), /digest/);
});
