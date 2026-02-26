---
applyTo: "dotnet/src/Microsoft.Agents.AI.DurableTask/**,dotnet/src/Microsoft.Agents.AI.Hosting.AzureFunctions/**"
---

# Durable Task area code instructions

The following guidelines apply to pull requests that modify files under
`dotnet/src/Microsoft.Agents.AI.DurableTask/**` or
`dotnet/src/Microsoft.Agents.AI.Hosting.AzureFunctions/**`:

## CHANGELOG.md

- Each pull request that modifies code should add just one bulleted entry to the `CHANGELOG.md` file containing a change title (usually the PR title) and a link to the PR itself.
- New PRs should be added to the top of the `CHANGELOG.md` file under a "## [Unreleased]" heading.
- If the PR is the first since the last release, the existing "## [Unreleased]" heading should be replaced with a "## v[X.Y.Z]" heading and the PRs since the last release should be added to the new "## [Unreleased]" heading.
- The style of new `CHANGELOG.md` entries should match the style of the other entries in the file.
- If the PR introduces a breaking change, the changelog entry should be prefixed with "[BREAKING]".
