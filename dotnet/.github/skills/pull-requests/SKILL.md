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
[`.github/pull_request_template.md`](../../../../.github/pull_request_template.md). Keep its
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
`Closes #123`) so it closes automatically on merge. For a non-trivial change,
confirm that a maintainer added the `ready-for-implementation` label or explicitly
agreed with the direction in an issue comment. A PR with no agreed issue may be
closed without detailed review. Before opening, confirm there is no other open PR
for the same issue; if there is, explain how this PR differs.

For a trivial change that does not require an issue, replace the `Fixes #`
placeholder with `N/A - trivial change` and briefly explain why the change is an
obvious correction whose desired result is not reasonably in dispute.

For repository-maintained scheduled automation, replace the placeholder with
`N/A - repository automation` and identify the generating workflow.

### `### AI Assistance`
Check exactly one option:
- Select **"No material AI assistance was used."** only when generative AI did
  not create or substantially transform submitted content.
- Otherwise select **"This is an AI-assisted contribution."** and briefly
  identify the assisted areas.

Generating or substantially editing the PR description with Copilot counts as
material AI assistance even if the implementation itself was not AI-assisted.
Never include prompts or sensitive information in the disclosure.

### `### Contribution Checklist`
Check every item that applies. Confirm that the PR links to an agreed issue or
documents a trivial-change or repository-automation exception. For the
breaking-change item:
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
   was addressed, preferably citing the commit containing the change. If the
   feedback was not addressed, explain why. Leave no comment unanswered.
6. **Resolve completed threads yourself.** After replying and completing any
   necessary discussion, resolve the review thread. Do not wait for the reviewer
   or a maintainer to resolve it. Leave a thread open only while it has an
   unanswered question or active discussion.

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
