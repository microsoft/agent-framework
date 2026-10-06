---
name: community-projects
description: >
  Normative eligibility and review checklist for external projects listed in
  the Python and .NET Agent Framework community-project catalogs.
---

# Community Project Catalog Review

Use this skill when reviewing either SDK catalog:

- [`python/samples/community-projects.md`](../../../python/samples/community-projects.md)
- [`dotnet/samples/community-projects.md`](../../../dotnet/samples/community-projects.md)

Also use it when an issue or pull request proposes adding an external project,
even if neither catalog file has changed yet.

The Agent Framework team syncs these source catalogs to the Microsoft Learn
documentation repository. Contributors should make catalog changes in this
repository rather than editing the synced copies directly.

## Required disclaimer

Each catalog must include this disclaimer before its first project table:

> [!IMPORTANT]
> The projects on this page are created and maintained outside the Microsoft
> Agent Framework team. Microsoft doesn't own, test, or support these projects.
> Listing a project doesn't imply Microsoft endorsement or confirm compatibility
> with any Agent Framework version. For compatibility information, support, and
> issue handling, contact the project maintainer through the project's
> repository and issue tracker.
> For security concerns, follow the maintainer's security reporting guidance.

## Catalog structure

- Organize entries only by their primary Agent Framework component:
  `Model providers`, `Agent services`, `Tools`, `Context providers`,
  `Vector stores`, `Middleware`, `Evaluation`, or `UI`.
- Do not add a provider-based view or group entries by company or service.
- Include only component sections that contain at least one eligible project.
- Use a project in one primary component only. Mention secondary scenarios in
  the `Scenarios` cell instead of duplicating the row.
- Every table must have exactly these columns, in this order:
  `Name`, `Brief description`, `Scenarios`, `Project`, `Issues`.
- Sort rows alphabetically by project name within each component.

## Eligibility requirements

An entry is eligible only when all of these checks pass:

1. The project page or repository linked from the catalog is public and
   available to readers.
2. The integration is published and reader-facing, not merely proposed,
   planned, under development, or described in an issue.
3. The published integration actually supports the SDK catalog where it is
   listed. Verify Python support for the Python page and .NET support for the
   .NET page from package metadata, source, or published documentation.
4. The `Project` link points directly to the public project, repository,
   package, or integration documentation that lets a reader use and evaluate
   the Agent Framework integration.
5. The `Issues` link opens the external project's issue-creation flow directly,
   such as a repository's `/issues/new` or `/issues/new/choose` page. A general
   issues list, discussion page, contact form, or Microsoft repository is not a
   substitute.
6. The name, description, and scenarios use neutral, factual wording. They
   must not state or imply Microsoft ownership, endorsement, testing, support,
   security review, or compatibility with any Agent Framework version.

Do not approve an entry from an issue proposal or maintainer assertion alone.
Open and verify the published reader-facing project, SDK-specific integration,
project link, and issue-creation link.

## Exclusions

Do not list:

- Services that only expose an OpenAI-compatible endpoint usable through an
  existing Agent Framework OpenAI client with a custom base URL. Those services
  should document that setup on their own site.
- Observability providers that only accept standard OpenTelemetry or OTLP
  configuration. Those providers should document that setup on their own site.
- Official Microsoft-owned integrations.
- Unpublished, planned, proposed, or otherwise unavailable projects.
- Projects that direct support or issue reports to a Microsoft repository,
  including `microsoft/agent-framework`.
- Generic feature requests, compatibility claims, example snippets, or service
  documentation that do not provide a published SDK-specific integration.

## Review procedure

1. Read the proposal, linked issue, and maintainer comments for context, but
   treat them only as leads.
2. Inspect the published project and any linked repository. Verify public
   access, current reader-facing installation or usage guidance, and concrete
   support for the SDK page being changed.
3. Open the proposed `Project` and `Issues` URLs. Confirm the latter is a direct
   issue-creation flow owned by the external project.
4. Check the row against the allowed components, exact table columns, neutral
   wording, alphabetical ordering, and one-primary-component rule.
5. Compare the Python and .NET catalogs. Keep shared names, descriptions,
   scenarios, project links, and issue links consistent when the same published
   project supports both SDKs. Do not copy an entry across SDK pages without
   independently verifying that SDK's published integration.
6. Recheck the exclusion list before assigning a verdict.

## Review output

Report every check using this table:

| Rule | Result | Evidence |
| --- | --- | --- |
| Public project and repository | Pass / Fail | Verified URLs and observations |
| Published SDK-specific integration | Pass / Fail | Package, source, or documentation evidence |
| Direct external issue-creation link | Pass / Fail | Verified issue-creation URL |
| Allowed primary component and table shape | Pass / Fail | Component, columns, and placement |
| Neutral wording | Pass / Fail | Wording review |
| Exclusions | Pass / Fail | Applicable exclusion checks |
| Ordering and cross-SDK consistency | Pass / Fail | Ordering and comparison evidence |

Finish with exactly one verdict:

- `Eligible` — every requirement passes.
- `Needs changes` — the published project is potentially eligible, but the
  proposed row, links, placement, or wording must be corrected.
- `Not eligible` — the project fails a substantive eligibility requirement or
  matches an exclusion.
