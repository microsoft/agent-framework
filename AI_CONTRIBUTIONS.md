# AI-Assisted Contributions Policy

AI tools may be used to prepare contributions to Microsoft Agent Framework. Their
use does not lower the project's quality bar, transfer responsibility to the
tool, or create an entitlement to review or acceptance.

This policy applies to issues, pull requests, code, tests, documentation,
samples, and other content submitted to this repository. It supplements the
[Contribution Guidelines](./CONTRIBUTING.md), [Code of Conduct](./CODE_OF_CONDUCT.md),
and [Security Policy](./SECURITY.md).

## What Counts as AI-Assisted

A contribution is materially AI-assisted when a generative AI tool creates or
substantially transforms content that is submitted to the repository. This can
include code, tests, documentation, designs, issue reports, and pull request
descriptions.

Routine spelling or grammar correction, formatting, search, and short editor
completions do not need to be disclosed unless the generated output materially
shaped the contribution.

## Contributor Responsibilities

### Disclose Material AI Assistance

Disclose material AI assistance in the issue or pull request description. For a
pull request, complete the **AI Assistance** section of the pull request
template and check exactly one option. Briefly identify the parts of the
contribution that were assisted, such as the issue analysis, implementation,
tests, documentation, or proposed design. Do not include prompts, credentials,
private data, or other sensitive information in the disclosure.

Disclosure is not a mark against a contribution. It gives reviewers useful
context and confirms that the contributor accepts responsibility for the
submitted work.

### Understand and Own the Contribution

The human contributor remains the accountable submitter. Contributors must:

- Review all submitted content rather than forwarding generated output.
- Understand the behavior, design, and consequences of the change.
- Be able to explain the change and respond to review feedback themselves.
- Make requested revisions and maintain the contribution through review.

"The AI generated it" is not an explanation for a design choice, defect, or
unnecessary change.

### Verify Correctness and Quality

AI-assisted contributions must meet the same standards as any other
contribution. Before submission, contributors must:

- Confirm that the change addresses a real, documented problem.
- Personally verify reported behavior and provide authentic reproduction details.
- Validate APIs, facts, versions, links, examples, and technical claims.
- Run the relevant builds, tests, formatting, and static analysis.
- Add meaningful tests when behavior changes.
- Remove unrelated changes, speculative abstractions, and generated churn.
- Check that comments and documentation describe the implemented behavior.

Generated tests are not sufficient merely because they pass. They must exercise
the intended behavior and be capable of detecting a broken implementation.

### Protect Confidential and Security-Sensitive Information

Do not provide an AI service with secrets, credentials, personal data, private
source code, non-public telemetry, embargoed vulnerabilities, or other
confidential information unless you are explicitly authorized to do so.

Security vulnerabilities must be reported through the process in
[SECURITY.md](./SECURITY.md), not through public issues, pull requests, or AI
service transcripts.

Contributors are responsible for complying with applicable organizational
policies and the terms of the AI tools they use.

### Respect Licensing and Provenance

Contributors must have the right to submit all content under the repository's
[license](./LICENSE). Review generated content for copied or closely reproduced
third-party code, text, notices, or other material whose license is incompatible
with this repository.

AI tool output does not remove attribution or licensing obligations. If the
origin or licensing of generated material is unclear, do not submit it.

### Follow the Contribution Workflow

AI tools make it inexpensive to produce changes. They do not make those changes
necessary.

For non-trivial changes, start with an issue and wait for a maintainer to add
the `ready-for-implementation` label or explicitly agree with the direction
before opening a pull request, as described in the
[Contribution Guidelines](./CONTRIBUTING.md). Keep each contribution focused on
one agreed problem.

Do not use AI tools to produce:

- Bulk or speculative pull requests.
- Duplicate or low-information issues.
- Broad refactors without prior agreement.
- Fabricated reproductions, benchmarks, citations, or test results.
- Changes that the contributor cannot explain or support through review.

## Maintainer Response

Maintainers evaluate the contribution, not the tool used to produce it. They may
ask for a reproduction, supporting evidence, a smaller scope, additional tests,
or a clearer explanation before reviewing implementation details.

Contributions may be closed without detailed review when they do not follow this
policy or the Contribution Guidelines. This includes undisclosed material AI
assistance, unverified generated content, speculative changes without an
agreed issue, and repeated low-quality or high-volume submissions.

This policy relies on honest disclosure rather than speculation about whether a
particular writing or coding style came from an AI tool.
