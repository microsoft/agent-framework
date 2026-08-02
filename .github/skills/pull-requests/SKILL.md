---
name: pull-requests
description: >
  Guidance for creating pull requests and handling PR review comments in the
  Agent Framework repository. Use this when writing a PR description (filling out
  the PR template) or when responding to and resolving review comments on an
  existing PR.
---

# Pull Request Workflow

This skill covers two tasks: (1) writing a high-quality PR description, and
(2) handling review comments on an existing PR.

## 1. Writing the PR description

Always follow the repository PR template at
[`.github/pull_request_template.md`](../../pull_request_template.md). Keep its
exact structure and headings. Fill every section:

### `### Motivation & Context`
Explain *why* the change is needed: the problem it solves and the scenario it
contributes to. Describe the net change relative to `main` — this is implied, so
do **not** spell out "vs main" explicitly.

### `### Description & Review Guide`
Describe the changes, the overall approach, and the design. Answer the three
prompts:
- **What are the major changes?**
- **What is the impact of these changes?**
- **What do you want reviewers to focus on?** — This item is for **human
  reviewers only**. Automated/AI reviewers must ignore it and review the entire
  change rather than narrowing scope to it.

### `### Related Issue`
Link the issue the PR fixes using a GitHub closing keyword (`Fixes #123` /
`Closes #123`) so it closes automatically on merge. A PR with no linked issue may
be closed regardless of how valid the change is. Before opening, confirm there is
no other open PR for the same issue; if there is, explain how this PR differs.

### `### Contribution Checklist`
Check every item that applies. For the breaking-change item:
- Leave **"This is not a breaking change."** checked for the common case.
- If the change **is** breaking, add the `breaking change` label **or** put
  `[BREAKING]` in the title prefix, before or after a language prefix such as
  `Python:` or `.NET:` — workflows keep the label and the title prefix in sync
  automatically (see `.github/workflows/label-title-prefix.yml` and
  `.github/workflows/label-pr.yml`).

### Do not
- Do **not** add ad-hoc sections such as "Validation" or "Tests run"; CI/CD and
  the checklist already cover validation status.
- Do **not** remove or reorder the template's headings.

### Creating the PR
Open new PRs as **drafts** until they are ready for review. Example:

```bash
gh pr create --repo microsoft/agent-framework --base main \
  --head <your-fork-owner>:<branch> --draft \
  --title "<concise title>" --body "<body following the template>"
```

## 2. Handling review comments

When a PR receives review comments, follow this sequence — **do not start editing
code before the user has reviewed the plan**:

1. **Review the comments.** Read every review comment and thread on the PR,
   including inline code comments and general review summaries.
2. **Make a plan.** Produce a concrete plan describing how each comment will be
   addressed (or why it should not be, with reasoning).
3. **Let the user review the plan.** Present the plan and wait for the user's
   approval or adjustments before implementing anything.
4. **Implement.** Make the agreed changes.
5. **Reply to every comment.** Add a reply to **all** comments explaining how it
   was addressed (or the agreed outcome) — leave none unanswered.
6. **Resolve resolved threads.** Mark a review thread as resolved only when the
   comment has actually been addressed.

### Useful commands

List review comments and threads:

```bash
# Inline review comments
gh api repos/{owner}/{repo}/pulls/{pr}/comments

# Review threads with resolution state (GraphQL)
gh api graphql -f query='
  query($owner:String!,$repo:String!,$pr:Int!){
    repository(owner:$owner,name:$repo){
      pullRequest(number:$pr){
        reviewThreads(first:100){
          nodes{ id isResolved comments(first:50){ nodes{ id body author{login} } } }
        }
      }
    }
  }' -F owner={owner} -F repo={repo} -F pr={pr}
```

Reply to an inline review comment:

```bash
gh api repos/{owner}/{repo}/pulls/{pr}/comments/{comment_id}/replies \
  -f body="Addressed in <commit>: <explanation>"
```

Resolve a review thread (needs the thread node id from the GraphQL query above):

```bash
gh api graphql -f query='
  mutation($threadId:ID!){
    resolveReviewThread(input:{threadId:$threadId}){ thread{ isResolved } }
  }' -F threadId={thread_id}
```
