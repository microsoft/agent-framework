---
name: cross-language-parity
description: >
  Guidance for checking whether issues and pull requests affecting the .NET or
  Python implementation of Agent Framework also apply to the other language, and
  for creating linked porting pull requests when parity work is clearly needed.
---

# Cross-Language Parity Workflow

Agent Framework has two product implementations:

- `dotnet/` contains the C#/.NET implementation.
- `python/` contains the Python implementation.

Use this skill when an issue, pull request, or review task asks whether behavior,
tests, APIs, bugs, or implementation changes in one language also apply to the
other language.

## Core rules

- Treat .NET and Python as sibling implementations of the same product, not as
  unrelated codebases.
- Prefer evidence from tests, public API shape, examples, docs, and analogous
  implementation code over filename similarity alone.
- Do not claim parity or non-parity from naming alone. Cite concrete files,
  symbols, tests, behavior, or missing counterparts.
- Never auto-port on low confidence. If the counterpart behavior is unclear,
  report what is known and ask for human review.
- When a port is clearly needed, create a separate draft pull request linked to
  the source issue or pull request.
- Keep automation comments concise and update an existing parity comment when
  possible instead of adding repeated comments.

## Language detection

Identify the source language from all available signals:

- Issue labels such as `dotnet`, `.NET`, `python`, or language-specific area
  labels.
- Pull request title prefixes such as `.NET:` or `Python:`.
- Changed paths under `dotnet/` or `python/`.
- Issue body, stack traces, package names, test paths, and snippets.

If both languages are affected already, report that this is a cross-language
change and still verify that the implementation and tests are complete in both
trees.

## 1. Issue parity check

Use this workflow for issues tagged or described as affecting one language.

1. Read the issue title, body, labels, linked discussions, and any reproduction
   details.
2. Determine the source language and target language.
3. Map the affected area to the closest counterpart in the other implementation:
   public APIs, abstractions, runtime components, serialization, integrations,
   samples, and tests.
4. Try to reproduce the issue in the target language when practical. Prefer a
   small targeted test or minimal snippet over broad test suites.
5. If direct reproduction is not practical, compare implementation behavior and
   existing tests to determine whether the same bug or feature gap likely exists.
6. Post or draft a parity comment using the structure below.

### Issue parity comment format

```markdown
<!-- copilot-cross-language-parity -->
### Cross-language parity check

**Source language:** <.NET|Python>
**Target language checked:** <Python|.NET>
**Applicability:** <Applies|Does not appear to apply|Unclear>
**Confidence:** <High|Medium|Low>

**Evidence**
- <specific file/test/API/repro evidence>
- <specific file/test/API/repro evidence>

**Reproduction**
<what was run or why direct reproduction was not practical>

**Recommended next step**
<no action needed|open a porting issue|create a linked port PR|needs maintainer input>
```

Use the hidden `<!-- copilot-cross-language-parity -->` marker so future runs can
find and update the existing comment.

## 2. Pull request parity review

Use this workflow when reviewing a pull request that primarily changes one
language implementation.

1. Read the PR title, body, linked issues, labels, and changed files.
2. Determine the source language and whether the PR already includes counterpart
   changes in the other language.
3. Compare tests first:
   - Identify changed or added source-language tests.
   - Find analogous tests in the target language.
   - Determine whether matching coverage exists, is missing, or is intentionally
     unnecessary.
4. Compare implementation:
   - Map changed public APIs, behavior, serialization, orchestration, runtime,
     and integration code to target-language counterparts.
   - Distinguish language-specific infrastructure from shared product behavior.
5. Decide one of:
   - `No port needed`: the change is language-specific or already covered.
   - `Port needed`: the change affects shared product behavior and the target
     language lacks the counterpart implementation or tests.
   - `Manual review needed`: the mapping or behavioral impact is ambiguous.
6. If a port is clearly needed, use the appropriate directional porting agent:
   - `dotnet-to-python-port` for .NET source changes that need Python parity.
   - `python-to-dotnet-port` for Python source changes that need .NET parity.

### PR parity comment format

```markdown
<!-- copilot-cross-language-parity -->
### Cross-language parity review

**Source language:** <.NET|Python|Both>
**Target language checked:** <Python|.NET|Both>
**Decision:** <No port needed|Port needed|Manual review needed>
**Confidence:** <High|Medium|Low>

**Test comparison**
- <source test evidence>
- <target test evidence or gap>

**Implementation comparison**
- <source implementation evidence>
- <target implementation evidence or gap>

**Follow-up**
<no action needed|draft port PR: #123|manual maintainer review needed>
```

## Port pull request requirements

When creating a port pull request:

- Open it as a draft.
- Link the original issue using `Fixes #<issue>` when the source PR fixed an
  issue.
- Link the source PR in the description using `Related to #<pr>`.
- Follow `.github/pull_request_template.md` exactly.
- Do not add ad-hoc validation sections.
- Include corresponding tests where possible.
- Keep the port surgical and avoid unrelated cleanup.
- Use the target language's local instructions:
  - `dotnet/AGENTS.md` for .NET changes.
  - `python/AGENTS.md` for Python changes.

## GitHub CLI helpers

Get issue details:

```bash
gh issue view <number> --repo microsoft/agent-framework \
  --json number,title,body,labels,comments,url
```

Get pull request details and changed files:

```bash
gh pr view <number> --repo microsoft/agent-framework \
  --json number,title,body,labels,files,headRefName,baseRefName,url,closingIssuesReferences
```

Find an existing parity comment:

```bash
gh api repos/microsoft/agent-framework/issues/<number>/comments \
  --jq '.[] | select(.body | contains("<!-- copilot-cross-language-parity -->")) | {id,body}'
```

Update an existing parity comment:

```bash
gh api repos/microsoft/agent-framework/issues/comments/<comment_id> \
  -X PATCH -f body=@comment.md
```

Create a new parity comment:

```bash
gh issue comment <number> --repo microsoft/agent-framework --body-file comment.md
```
