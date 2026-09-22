// Copyright (c) Microsoft. All rights reserved.

const { createHash } = require('node:crypto');

function parseRequest(body) {
  const text = typeof body === 'string' ? body.trim() : '';
  if (text === '/fix-ci') return { command: '/fix-ci', instructions: '' };
  const match = /^\/fix\s+([\s\S]+)$/.exec(text);
  const instructions = match?.[1].trim();
  return instructions && instructions.length <= 4000 ? { command: '/fix', instructions } : null;
}

function parseCommand(body) {
  return parseRequest(body)?.command ?? null;
}

function commentReferences(instructions, repo, prNumber) {
  const references = new Map();
  for (const raw of instructions.match(/https:\/\/github\.com\/[^\s<>()\[\]"']+/g) ?? []) {
    const url = new URL(raw.replace(/[.,;:]+$/, ''));
    const target = /^\/([^/]+)\/([^/]+)\/(pull|issues)\/([1-9][0-9]*)\/?$/.exec(url.pathname);
    if (!target) continue;
    if (`${target[1]}/${target[2]}` !== repo || Number(target[4]) !== prNumber || target[3] !== 'pull') {
      throw new Error('Comment reference must target this PR');
    }
    if (!url.hash) continue;
    const anchor = /^#(discussion_r|issuecomment-)([1-9][0-9]*)$/.exec(url.hash);
    if (!anchor || url.search || url.pathname.endsWith('/')) throw new Error('Unsupported comment reference');
    const id = Number(anchor[2]);
    if (!Number.isSafeInteger(id)) throw new Error('Invalid comment reference ID');
    references.set(url.href, { url: url.href, id, inline: anchor[1] === 'discussion_r' });
  }
  if (references.size > 5) throw new Error('At most five comment references are supported');
  return [...references.values()];
}

function validPath(path) {
  return typeof path === 'string' && path.length > 0 && !path.startsWith('/') &&
    !path.split('/').some(part => part === '..' || part === '.git') && !/[\\\x00-\x1f\x7f]/.test(path);
}

function validateComments(snapshot, instructions) {
  const references = commentReferences(instructions, snapshot.repo, snapshot.pr_number);
  const comments = snapshot.review_comments === undefined ? [] : snapshot.review_comments;
  if (!Array.isArray(comments) || comments.length !== references.length) throw new Error('Invalid frozen comments');
  const seen = new Set();
  for (const comment of comments) {
    const reference = references.find(item => item.url === comment.url);
    if (!reference || seen.has(comment.url) || comment.id !== reference.id || comment.author !== snapshot.requester ||
        typeof comment.body !== 'string' || comment.body.length > 8000 ||
        typeof comment.updated_at !== 'string' || !/^\d{4}-\d{2}-\d{2}T/.test(comment.updated_at) ||
        !Number.isFinite(Date.parse(comment.updated_at))) throw new Error('Invalid frozen comment identity');
    if (reference.inline ? (comment.commit_id !== snapshot.head_sha || !validPath(comment.path)) :
        (comment.commit_id !== null || comment.path !== null)) throw new Error('Invalid frozen comment revision');
    seen.add(comment.url);
  }
}

async function freezeComments({ github, context, instructions, headSha }) {
  const repo = `${context.repo.owner}/${context.repo.repo}`;
  const references = commentReferences(instructions, repo, context.payload.issue.number);
  const comments = [];
  for (const reference of references) {
    const endpoint = reference.inline ? github.rest.pulls.getReviewComment : github.rest.issues.getComment;
    const { data } = await endpoint({ ...context.repo, comment_id: reference.id });
    const targetUrl = `https://api.github.com/repos/${repo}/${reference.inline ? 'pulls' : 'issues'}/${context.payload.issue.number}`;
    if (data.id !== reference.id || data.html_url !== reference.url || data.user?.login !== context.payload.comment.user.login ||
        (reference.inline ? data.pull_request_url : data.issue_url) !== targetUrl ||
        (reference.inline && data.commit_id !== headSha)) throw new Error('Comment is foreign, stale, or not authored by requester');
    comments.push({ id: data.id, url: data.html_url, author: data.user.login, body: data.body,
      updated_at: data.updated_at, path: reference.inline ? data.path : null,
      commit_id: reference.inline ? data.commit_id : null });
  }
  return comments;
}

function digest(json) {
  return createHash('sha256').update(json, 'utf8').digest('hex');
}

function validate(snapshot) {
  if (snapshot.schema_version !== 1) throw new Error('Unsupported snapshot version');
  for (const key of ['repo', 'head_repo']) {
    if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(snapshot[key] || '')) {
      throw new Error(`Invalid ${key}`);
    }
  }
  for (const key of ['repo_id', 'head_repo_id', 'pr_number', 'comment_id']) {
    if (!Number.isSafeInteger(snapshot[key]) || snapshot[key] <= 0) throw new Error(`Invalid ${key}`);
  }
  for (const key of ['head_sha', 'base_sha', 'automation_sha']) {
    if (!/^[0-9a-f]{40}$/.test(snapshot[key] || '')) throw new Error(`Invalid ${key}`);
  }
  if (snapshot.devflow_sha !== undefined && !/^[0-9a-f]{40}$/.test(snapshot.devflow_sha)) throw new Error('Invalid controller SHA');
  if (snapshot.public_snapshot_sha256 !== undefined && (!snapshot.devflow_sha || !/^[0-9a-f]{64}$/.test(snapshot.public_snapshot_sha256))) throw new Error('Invalid public snapshot binding');
  if (snapshot.merge_sha !== null && !/^[0-9a-f]{40}$/.test(snapshot.merge_sha || '')) throw new Error('Invalid merge_sha');
  for (const key of ['head_ref', 'base_ref', 'requester']) {
    if (typeof snapshot[key] !== 'string' || !snapshot[key] || /[\x00-\x20\x7f]/.test(snapshot[key])) {
      throw new Error(`Invalid ${key}`);
    }
  }
  const request = parseRequest(snapshot.comment_body);
  if (!request || request.command !== snapshot.command || (snapshot.instructions === undefined ? '' : snapshot.instructions) !== request.instructions ||
      (snapshot.command === '/fix' && !Array.isArray(snapshot.review_comments))) throw new Error('Invalid command');
  validateComments(snapshot, request.instructions);
  return snapshot;
}

async function capture({ github, context }) {
  const { payload } = context;
  const request = parseRequest(payload.comment?.body);
  const command = request?.command;
  if (context.eventName !== 'issue_comment' || payload.action !== 'created' || !payload.issue?.pull_request || !command) {
    return null;
  }
  const { data: pr } = await github.rest.pulls.get({ ...context.repo, pull_number: payload.issue.number });
  const repo = `${context.repo.owner}/${context.repo.repo}`;
  if (pr.state !== 'open' || !pr.head.repo || pr.base.repo.full_name !== repo || pr.base.repo.id !== payload.repository.id) {
    throw new Error('PR is closed or repository identity does not match');
  }
  const reviewComments = await freezeComments({ github, context, instructions: request.instructions, headSha: pr.head.sha });
  const snapshot = validate({
    schema_version: 1,
    repo,
    repo_id: payload.repository.id,
    pr_number: payload.issue.number,
    head_repo: pr.head.repo.full_name,
    head_repo_id: pr.head.repo.id,
    head_ref: pr.head.ref,
    head_sha: pr.head.sha,
    base_ref: pr.base.ref,
    base_sha: pr.base.sha,
    merge_sha: pr.merge_commit_sha ?? null,
    requester: payload.comment.user.login,
    comment_id: payload.comment.id,
    command,
    instructions: request.instructions,
    review_comments: reviewComments,
    comment_body: payload.comment.body,
    automation_sha: context.sha,
  });
  const json = JSON.stringify(snapshot);
  if (Buffer.byteLength(json, 'utf8') > 98304) throw new Error('Snapshot exceeds size limit');
  return { snapshot, json, sha256: digest(json), base64: Buffer.from(json).toString('base64') };
}

function decode(base64, sha256, context) {
  if (typeof base64 !== 'string' || base64.length > 131072 || !/^[A-Za-z0-9+/]+={0,2}$/.test(base64)) {
    throw new Error('Invalid snapshot encoding');
  }
  const json = Buffer.from(base64, 'base64').toString('utf8');
  if (!/^[0-9a-f]{64}$/.test(sha256 || '') || digest(json) !== sha256) throw new Error('Snapshot digest mismatch');
  const snapshot = validate(JSON.parse(json));
  if (context && (snapshot.repo !== `${context.repo.owner}/${context.repo.repo}` ||
      snapshot.repo_id !== context.payload.repository.id ||
      snapshot.pr_number !== context.payload.issue.number ||
      snapshot.comment_id !== context.payload.comment.id ||
      snapshot.requester !== context.payload.comment.user.login ||
      snapshot.comment_body !== context.payload.comment.body ||
      snapshot.automation_sha !== context.sha)) {
    throw new Error('Snapshot event mismatch');
  }
  return { snapshot, json };
}

function bindController({ base64, sha256, context, devflowSha }) {
  const { snapshot } = decode(base64, sha256, context);
  if (snapshot.devflow_sha !== undefined || snapshot.public_snapshot_sha256 !== undefined) throw new Error('Snapshot already bound');
  const bound = validate({ ...snapshot, public_snapshot_sha256: sha256, devflow_sha: devflowSha });
  const json = JSON.stringify(bound);
  if (Buffer.byteLength(json, 'utf8') > 98304) throw new Error('Snapshot exceeds size limit');
  return { snapshot: bound, json, sha256: digest(json), base64: Buffer.from(json).toString('base64') };
}

function decodeBound({ base64, sha256, publicBase64, publicSha256, devflowSha, context }) {
  const expected = bindController({ base64: publicBase64, sha256: publicSha256, context, devflowSha });
  const decoded = decode(base64, sha256, context);
  if (decoded.json !== expected.json || sha256 !== expected.sha256) throw new Error('Authorized snapshot binding mismatch');
  return decoded;
}

async function authorize({ base64, sha256, context, github, core, teamSlug, checkTeamMembership }) {
  const { snapshot } = decode(base64, sha256, context);
  const result = await checkTeamMembership({
    github, context, core, teamSlug,
    issueNumber: snapshot.pr_number,
    username: snapshot.requester,
  });
  return result.isTeamMember && result.author === snapshot.requester;
}

module.exports = { parseRequest, parseCommand, capture, decode, bindController, decodeBound, authorize };
