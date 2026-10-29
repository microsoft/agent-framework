---
status: proposed
contact: eavanvalkenburg
date: 2026-10-29
deciders: [eavanvalkenburg]
informed: [Python release maintainers, engineering and architecture leads]
---

# Coordinate Python releases through a reviewed batch and one protected publisher

## Context and Problem Statement

Python distributions have independent versions, while release preparation already selects a batch through
CHANGELOG-driven version bumps. The GitHub published-release workflow currently builds and uploads assets after
the release is public. Production package publication needs protected Azure DevOps ESRP approval, and GitHub
must not receive credentials or federated permission to queue that pipeline.

## Decision Drivers

- Review selected packages, versions, and public smoke imports in the same version-bump PR.
- Build once and publish those exact artifacts, not a later rebuild.
- Preserve maintainer-written release notes and keep the release a draft until verification succeeds.
- Use one overall tag and one protected run for the whole batch, without adding GitHub-to-Azure DevOps authority.

## Considered Options

- Keep the GitHub post-publication asset builder. This preserves current behavior, but creates competing artifact
  paths and exposes a public release before its verified artifacts are attached.
- Queue per-package runs from GitHub. This gives independent queues but duplicates batch selection and approvals,
  introduces race conditions, and requires forbidden cross-system credentials.
- Check in a generated batch manifest and let Azure DevOps discover eligible existing drafts and tags. This
  requires coordinated rollout and durable claims, but preserves a single reviewed selection and publisher.

## Decision Outcome

Proposed option: **generated batch manifest with Azure DevOps discovery and publication**.

`python/.github/release-<fulltag>.json` contains the expected overall `python-<version>` tag, canonical distribution names mapped
to their exact metadata versions, and optional additive public `module:export` smoke checks. The release tooling
generates all selected smoke checks and derives versions from the existing changed-metadata selection, excluding
dependency-only edits whose version did not change. The source manifest does not contain its own commit SHA.
For `python-1.24.0`, its path is `python/.github/release-python-1.24.0.json`. Earlier per-tag files remain unchanged
and browsable on `main`. PR checks validate exactly one new batch against current metadata and reject edits or
deletions of historical requests, without revalidating their old versions. These are intended release batches,
not evidence of successful publication. Producer and consumer derive the exact filename from the validated
expected full tag, never from latest-file scanning or a fixed-path fallback.

Azure DevOps resolves the existing tag, reads the manifest from that exact commit, claims the batch once, builds,
checks isolated installs/imports, obtains protected approval, publishes through ESRP, and verifies publication.
It then uploads the retained exact artifacts and output artifact manifest to the existing draft and changes
only its draft status, preserving the human-written title/body and prerelease flag. PyPI absence validates the
batch; it does not select packages. Partial publication requires reconciliation, not a new selection or rebuild.

GitHub performs read-only PR and published-tag contract checks. The previous asset builder and local production
publish tasks are retired. Public runtime APIs and package versions do not change as part of this infrastructure
change. The standalone Lab workspace remains outside the coordinated release batch.

Merge the disabled Azure DevOps consumer first, then the upstream producer and old-publisher retirement.
Reuse the existing `github-agent-framework` Azure DevOps GitHub service connection used by the .NET release
pipeline, with explicit authorization for the Python pipelines and verification of repository/release access.
Do not introduce a separate GitHub App, private key, or Key Vault token-minting setup. Azure identity for durable
Blob claims and protected ESRP gates remains separate operator setup. Connection reuse does not replace the
asset-only REST finalizer with a task that rewrites release notes, prerelease flags, or existing assets.
Verify that setup before choosing the first eligible draft ID and activating discovery last. Neither PR
authorizes production tags, drafts, publication, or infrastructure changes.
The [release skill](../../python/.github/skills/agent-framework-py-release/SKILL.md) contains the operator procedure
and recovery requirements. Maintainer and engineering/architecture approval is required before accepting this ADR.
