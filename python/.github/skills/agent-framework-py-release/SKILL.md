---
name: agent-framework-py-release
description: Use when cutting a Python release for the microsoft/agent-framework monorepo. Triggers on "bump py versions", "cut a python release", "prepare release PR for python", "release py packages", "bump python to X.Y.Z", or similar requests to bump Python package versions and prepare a release PR. Handles all four lifecycle tiers with CHANGELOG-driven selective bumps, a reviewed batch manifest, dependency checks, and the protected Azure DevOps release handoff.
---

# Agent Framework Python Release

Cuts a Python release PR for the `microsoft/agent-framework` monorepo.

Release preparation does **not** authorize production tags, draft creation, publication, or deployment. Stop at the
requested PR unless a maintainer separately authorizes the release handoff below.

## Core principle: CHANGELOG drives bumps

**No more universal lockstep.** A package only bumps if it has a CHANGELOG entry this cycle. Draft the CHANGELOG first, then derive the bump list from it.

Exceptions to selective bumping (these stay coupled regardless of per-package changes):

- **Root `agent-framework` is coupled to `agent-framework-core` via `agent-framework-core[all]==X.Y.Z`** (exact pin in `python/pyproject.toml`). If `core` bumps, root bumps. Root may also bump independently for its own changes (docs/metadata/extras).
- **Beta-tier cohort bumps are still allowed** when the user explicitly wants a fresh date stamp across all betas for cohort signaling — but this is a deliberate user decision per release, not a default.

If the user explicitly states which packages to bump (or hands over a PR list per package), treat that as authoritative.

## Lifecycle tiers and version rules

Use `python/.github/skills/python-package-management/SKILL.md` as the source of truth for lifecycle
version patterns, date-stamp cutoffs, classifier alignment, and internal dependency updates.

For release work, derive the live tier map at release time from `python/PACKAGE_STATUS.md` and the actual
`version =` lines in each `pyproject.toml`. Do not hardcode counts — packages move between tiers.

## Inputs to confirm before bumping

1. **The changeset**: explicit commits/PRs the release covers, OR derive from `git log ${LAST_RELEASED_TAG}..${RELEASE_BASE} -- python/`.
2. **Per-package CHANGELOG entries**: which packages will get a line in the new release section. This list IS the bump list.
3. **Per-released-package semver bump**: for each released-tier package that has a CHANGELOG entry, decide PATCH / MINOR / MAJOR.
4. **Date stamp** (only if any alpha/beta is being bumped): default from the `python-package-management`
   date-stamp rule.
5. **Optional cohort bump?**: ask if betas should all get a new date stamp regardless of per-package changes. Default: no.

If the user states target versions or a date explicitly, use exactly what they said — do not "correct" based on historical timezones.

## Non-negotiable rules

- **Release workflow owns the CHANGELOG**: individual feature/fix PRs do not edit
  `python/CHANGELOG.md`; this workflow creates the entries centrally from merged changes.
- **CHANGELOG-driven bumps**: only packages mentioned in the new CHANGELOG section get version bumps. Exceptions: root follows core (==pin); user-opted cohort bump on betas.
- **Follow `python-package-management` for package lifecycle and versioning rules** — do not duplicate those
  rules in this release workflow.
- **No `Co-Authored-By` trailer** on any commit.
- **Use `uv run`** for cross-version Python/Poe commands and add the relevant
  `tooling/requirements-*.txt` bundle only for single-version tools.
- **Never rename an existing CHANGELOG section header** during a new release cut. Only INSERT a new section above existing ones.
- **Footer reference links are part of the CHANGELOG edit**, not optional.
- **One batch, one overall tag, one Azure DevOps run.** Generate `python/.github/release-<fulltag>.json` in the same
  version-bump PR. Keep earlier per-tag manifests unchanged for browsing release-batch history.
  Never replace the reviewed selection with "all versions absent from PyPI", per-package tags, or one run per package.
- **Azure DevOps is the only production publisher.** GitHub has no Azure DevOps API credentials or federated queue
  permission. The GitHub release workflow is read-only validation; local production `publish` tasks are retired.

## Workflow

### 1. Orient and create branch

```bash
git fetch origin main --tags --quiet
git fetch upstream main --tags --quiet 2>/dev/null || true
git status

# Fork clones use upstream/main as the authoritative release base; direct clones use origin/main.
if git show-ref --verify --quiet refs/remotes/upstream/main; then
  RELEASE_BASE=upstream/main
else
  RELEASE_BASE=origin/main
fi
git log -1 --oneline "$RELEASE_BASE"
```

If the user already has a `bump-py-ver-release-*` branch checked out, use it. Otherwise:

```bash
git checkout -b bump-py-ver-release-YYMMDD "$RELEASE_BASE"
```

### 2. Build the live tier map

Read `python/PACKAGE_STATUS.md` to enumerate current packages and lifecycle stages, and `grep '^version' python/pyproject.toml python/packages/*/pyproject.toml` to confirm actual versions. Cross-reference — if `PACKAGE_STATUS.md` shows a package as `beta` but its version looks like `1.0.0aYYMMDD`, surface the inconsistency before proceeding.

Watch for: new packages added since the last release, lifecycle transitions (alpha→beta, beta→rc, rc→released), and stale packages that haven't been touched in many cycles.

### 3. Identify changeset

Use the LATEST released tag as the compare base:

```bash
LAST_RELEASED_TAG=$(
  git tag -l 'python-*' \
    | uv run --directory python python -c 'import re, sys; tags=[t.strip() for t in sys.stdin if re.fullmatch(r"python-\d+\.\d+\.\d+", t.strip())]; print(max(tags, key=lambda t: tuple(map(int, t[7:].split(".")))))'
)
echo "Compare base: $LAST_RELEASED_TAG"
```

List commits and packages touched:

```bash
git log --oneline ${LAST_RELEASED_TAG}..${RELEASE_BASE} -- python/ ':!python/CHANGELOG.md'

# Per-commit package footprint
for sha in $(git log --format='%H' ${LAST_RELEASED_TAG}..${RELEASE_BASE} -- python/); do
  echo "--- $(git show -s --format='%h %s' $sha) ---"
  git show --name-only --format='' $sha | grep '^python/packages/' | \
    sed 's|^python/packages/||' | awk -F/ '{print $1}' | sort -u
done
```

When both remotes exist, record whether the fork is behind the authoritative base:

```bash
git rev-list --left-right --count origin/main...upstream/main
```

If user provides an explicit commit/PR list, treat THAT as authoritative.

#### 3a. Build the authoritative touched-package set

Aggregate the per-commit footprint into a single union across the whole range. This is the **source of truth** for what must appear in the CHANGELOG. Save it before drafting entries.

```bash
# Union of all touched package directories across the range
git log --name-only --format='' ${LAST_RELEASED_TAG}..${RELEASE_BASE} -- python/packages/ \
  | grep '^python/packages/' \
  | sed 's|^python/packages/||' \
  | awk -F/ '{print $1}' \
  | sort -u

# Root-level files (drive a root agent-framework entry if substantive)
git log --name-only --format='' ${LAST_RELEASED_TAG}..${RELEASE_BASE} \
  -- python/pyproject.toml python/agent_framework_meta/ python/README.md \
  2>/dev/null | grep -v '^$' | sort -u
```

**What "touched" means for bump purposes** (apply judgment, document in commit message):

| Change scope under `python/packages/<pkg>/` | Drives a bump? |
| --- | --- |
| Source code under `<pkg>/agent_framework_*` or the package's library tree | **Yes** — ship-affecting |
| `pyproject.toml` (deps, classifiers, extras, version metadata) | **Yes** — publishes new metadata |
| `README.md` substantive changes (env vars, install instructions, usage) | **Yes** — user-facing |
| `README.md` typo/wording-only | Judgment — usually no, but record under `### Changed` if you do bump |
| Tests only (`tests/`) | Usually no — test changes don't ship to PyPI consumers. Bump only if the test change reflects a real behavior change in the package |
| Package-local samples (alpha packages only, before promotion) | **Yes** for alpha; samples ship with the alpha package |
| Repo infra touching the package dir (CI config, lint config) | No — record under `- **tests**:`, `- **samples**:`, or `- **docs**:` instead |

Root `agent-framework` is touched when `python/pyproject.toml`, `python/agent_framework_meta/`, or root `README.md` substantive content changed.

### 4. Draft CHANGELOG entries (THIS DRIVES THE BUMP LIST)

Individual feature/fix PRs intentionally do not add CHANGELOG entries. During release preparation, derive this section
centrally from the merged PRs since the last released tag.

Locate `## [Unreleased]` and the top existing release header. INSERT a new section between them.

**New section structure:**

```markdown
## [<release-label>] - YYYY-MM-DD

### Added
- **agent-framework-<pkg>**: <subject> ([#NNNN](https://github.com/microsoft/agent-framework/pull/NNNN))

### Changed
- **agent-framework-<pkg>**: ...

### Fixed
- **agent-framework-<pkg>**: ...
```

`<release-label>` is the released-tier target if any released package is bumping (e.g. `1.7.0`), or the date stamp (e.g. `1.0.0b260528`) if the release is prerelease-only. Reflect the user's framing.

**Categorization heuristics (read commit subject + PR title/body):**
- **Added**: new public APIs, new packages, new samples, `feat(...)`, new re-exports from `agent_framework`, new capabilities surfaced from underlying SDKs
- **Changed**: metadata/classifier corrections, dependency upgrades, test infra changes, signature adjustments on existing APIs, renames, doc updates, lifecycle transitions
- **Fixed**: `fix(...)`, bug/crash/regression repairs, noise reduction (e.g. stop emitting spurious warnings), protocol-compliance fixes
- **Removed**: deprecations/deletions (use `[BREAKING]` prefix if breaking)

**Entry format:**
- `- **agent-framework-<pkg>**: <subject, grammar-normalized> ([#NNNN](https://github.com/microsoft/agent-framework/pull/NNNN))`
- Multiple packages touched by one PR: comma-separated bold names at the head: `- **agent-framework-core**, **agent-framework-foundry**: ...`
- Root package changes: use `- **agent-framework**: ...`
- Test/sample/repo infra: `- **tests**: ...`, `- **samples**: ...`, `- **docs**: ...` (these do not drive package bumps)

**Once entries are drafted, the set of `**agent-framework-<pkg>**` and root `**agent-framework**` mentions IS the bump list.** Anything not mentioned does not bump.

#### 4a. Reconcile mentions against the touched-package set (DO NOT SKIP)

Before moving on, prove that every ship-affecting touched package has at least one CHANGELOG entry. A package whose code changed but is missing from CHANGELOG will NOT bump — and the fix will not ship to PyPI consumers.

```bash
# 1. Touched ship-affecting packages and root package files (from step 3a)
TOUCHED_PACKAGES=$(git log --name-only --format='' ${LAST_RELEASED_TAG}..${RELEASE_BASE} -- python/packages/ \
  | grep '^python/packages/' \
  | sed 's|^python/packages/||' \
  | awk -F/ '{print $1}' \
  | sort -u)

ROOT_TOUCHED=$(git log --name-only --format='' ${LAST_RELEASED_TAG}..${RELEASE_BASE} \
  -- python/pyproject.toml python/agent_framework_meta/ python/README.md \
  2>/dev/null | grep -v '^$' | sort -u)

TOUCHED=$(
  {
    if [ -n "$TOUCHED_PACKAGES" ]; then echo "$TOUCHED_PACKAGES"; fi
    if [ -n "$ROOT_TOUCHED" ]; then echo "agent-framework"; fi
  } | sort -u
)

# 2. Packages mentioned in the new CHANGELOG section
# (Extract from the section you just drafted — adjust the awk range to the new section's bounds)
MENTIONED=$(awk '
  /^## \[<release-label>\]/ { in_section=1; next }
  in_section && /^## \[/ { exit }
  in_section { print }
' python/CHANGELOG.md \
  | grep -oE '\*\*agent-framework(-[a-z0-9_-]+)?\*\*' \
  | sed 's/\*\*//g;s/^agent-framework-//' \
  | sort -u)

# 3. Diff — anything in TOUCHED but missing from MENTIONED is a gap
comm -23 <(echo "$TOUCHED") <(echo "$MENTIONED")
```

For every gap, decide explicitly with the user:

- **Add a CHANGELOG entry and bump** — the default. Even small package changes (a dep upgrade, a metadata fix) deserve an entry under `### Changed`.
- **Intentionally skip** — only when the touched files are demonstrably non-shipping (e.g. comments-only, test infra). Note the skip in the commit message body so reviewers see the reasoning.

Package-name aliasing to watch for: directory `foundry_local` → package `agent-framework-foundry-local`; `github_copilot` → `agent-framework-github-copilot`; `azure-ai-search` → `agent-framework-azure-ai-search`. The directory name and the published PyPI name are not always identical — confirm both when reconciling.

**Footer reference links** (REQUIRED every release):

```bash
grep -n "^\[.*\]:" python/CHANGELOG.md | head -5
```

Two edits when a released-tier bump is in play:
1. Advance `[Unreleased]` compare base from `python-${OLD_RELEASED}...HEAD` to `python-${NEW_RELEASED}...HEAD`.
2. INSERT a new `[${NEW_RELEASED}]` line ABOVE the previous version's link: `[${NEW_RELEASED}]: https://github.com/microsoft/agent-framework/compare/python-${OLD_RELEASED}...python-${NEW_RELEASED}`

For prerelease-only releases (no released-tier bump this cycle), footer links don't change.

### 5. Apply bumps per tier

For each package in the bump list, choose the rule for its current tier. Use anchored `sed` (`^version = "..."$`) so only the project's own version matches. Use `sed -i.bak` plus backup cleanup for portable in-place edits across macOS/BSD sed and GNU sed.

**Released tier (per-package semver):**

```bash
# Example: openai goes 1.6.0 -> 1.6.1 (PATCH); core stays
sed -i.bak 's/^version = "1.6.0"$/version = "1.6.1"/' python/packages/openai/pyproject.toml
rm python/packages/openai/pyproject.toml.bak
```

**Root `agent-framework` (only when `core` bumps, OR for its own changes):**

```bash
sed -i.bak "s/^version = \"${OLD_ROOT}\"$/version = \"${NEW_ROOT}\"/" python/pyproject.toml
# AND keep the exact pin in sync with core
sed -i.bak "s/agent-framework-core\\[all\\]==${OLD_CORE}/agent-framework-core[all]==${NEW_CORE}/" python/pyproject.toml
rm python/pyproject.toml.bak
```

**RC tier (counter increment):**

```bash
# ag-ui goes 1.0.0rc3 -> 1.0.0rc4 only because it has a CHANGELOG entry
sed -i.bak 's/^version = "1.0.0rc3"$/version = "1.0.0rc4"/' python/packages/ag-ui/pyproject.toml
rm python/packages/ag-ui/pyproject.toml.bak
```

**Alpha/Beta tier (new date stamp):**

```bash
OLD_DATE=260521
NEW_DATE=260528

# Only the packages with CHANGELOG entries get the new stamp.
# Example: anthropic and bedrock had entries, others did not.
for pkg in anthropic bedrock; do
  file="python/packages/$pkg/pyproject.toml"
  sed -i.bak "s/1\\.0\\.0b${OLD_DATE}/1.0.0b${NEW_DATE}/g" "$file"
  rm "${file}.bak"
done
```

If the user opts into a cohort-wide beta bump regardless of per-package changes, enumerate every beta package from `PACKAGE_STATUS.md` and stamp all of them. State that this is a cohort bump in the commit message.

Spot-check with `grep '^version' python/pyproject.toml python/packages/*/pyproject.toml | sort` before moving on.

### 5a. Refresh the `core[all]` release cohort

When Core bumps, update every Agent Framework dependency in
`python/packages/core/pyproject.toml` `[project.optional-dependencies].all`:

- Workspace packages use their post-bump version as the lower bound, or their unchanged current version when they
  are not otherwise releasing this cycle.
- External Agent Framework packages such as Azure Functions and Durable Task retain a bounded known-good floor.
- Every entry keeps an upper bound for its supported major version.
- Preserve environment markers for packages that do not support every Python/platform combination.

These bounds prevent pip from backtracking across old cyclic `core[all] -> integration -> core` combinations. The
release validator rejects missing, stale, or unbounded cohort entries.

### 6. Floor bound updates on `agent-framework-core`

Only relevant when `core` itself bumped this cycle. Two policies, pick one explicitly with the user:

- **Conservative (default)**: raise `agent-framework-core>=X.Y.Z` to the new core version on every non-core package that is ALSO bumping this cycle. Leaves packages-not-bumped at their existing floor.
- **Strict per-upstream-doc**: only raise the floor on packages that actually consume a new core API introduced in the bump. This requires per-package code inspection because release probes use the co-released local core and cannot prove compatibility with an older published core floor.

When raising a core floor, replace only the `>=OLD` half of the bound you intend to change:

```bash
file="python/packages/<pkg>/pyproject.toml"
sed -i.bak "s/agent-framework-core>=${OLD_CORE}/agent-framework-core>=${NEW_CORE}/" "$file"
rm "${file}.bak"
```

If `core` did not bump this cycle, do not touch floors.

### 7. Generate the reviewed release batch and validate

After applying the selected bumps and dependency edits, stage any new workspace package metadata with
`git add python/packages/<package>/pyproject.toml`. The generator fails explicitly if workspace metadata is still
untracked, rather than silently omitting that distribution. Existing tracked metadata need not be staged.
Generate the manifest from that same metadata diff:

```bash
RELEASE_TAG="python-<release-label>"
uv run --directory python --group tool-runtime poe prepare-python-release --base-ref "$RELEASE_BASE" --tag "$RELEASE_TAG"
```

The generator reuses the release validator's changed-`pyproject.toml` selection, then includes only packages whose
version increased (or new workspace packages). Compare package identity by canonical distribution name, not directory:
a move does not make an existing version new, and a renamed distribution is a new identity. Dependency-only metadata
edits remain part of dependency validation but do not select an unchanged version for publication. The generator
rejects a Core release without a version increase for root `agent-framework`; the explicit cohort decision above
still determines other bumps. The excluded standalone Lab workspace is not part of this batch.

Commit **`python/.github/release-${RELEASE_TAG}.json` in this same PR**, together with the version and lockfile changes.
The filename includes the full tag: `python-1.24.0` produces `python/.github/release-python-1.24.0.json`.
Do not maintain a duplicate list of versions manually. Regenerate the new file after changing the bump list while
the PR is open. Once it is part of the release base, it is historical: never edit, replace, or delete it.
For example, `python/.github/release-python-1.24.0.json` contains:

```json
{
  "tag": "python-1.24.0",
  "packages": {
    "agent-framework": "1.24.0",
    "agent-framework-core": "1.24.0",
    "agent-framework-foundry": "1.16.0"
  },
  "smoke_imports": {
    "agent-framework": ["agent_framework:Agent"],
    "agent-framework-core": ["agent_framework:Message"],
    "agent-framework-foundry": ["agent_framework.foundry:FoundryAgent"]
  }
}
```

Contract:

- `tag` and non-empty `packages` are required. The tag is one overall `python-<PEP440-version>` release label, not
  a requirement that every selected distribution share a version. No source commit SHA is stored in this file:
  Azure DevOps resolves the immutable tagged commit and reads `python/.github/release-<fulltag>.json` there.
  Both sides derive this exact path from the expected full tag. Never scan for the latest file or fall back to
  the old fixed `.github/release.json` or root `release.json` paths.
  Generation and PR validation reject tags already present in the freshly fetched local tag refs. Fetch tags as in
  step 1 before preparation. Published-release validation permits its existing tag and checks the qualified
  `refs/tags/<fulltag>` revision; PR checks use the immutable event SHA, not a moving merge ref.
- Keys are exact canonical distribution names; values are PEP 440 strings equal to the tagged `project.version`.
  The expected tag must match the manifest tag, preventing reuse of a stale batch. PyPI absence is validation,
  **never selection**.
- `smoke_imports` is an optional additive map of public `module:export` checks (classes or functions). The generator
  emits it for **every** selected distribution. The consumer only has built-in defaults for meta/core/Foundry;
  other packages require explicit reviewed checks. Unknown packages fail until `scripts/prepare_release.py`
  has a reviewed public import entry. A check imports the module and resolves the export, without creating an
  agent, opening a connection, or calling a service.
- Prefer public `agent_framework.*` bridges. Never derive checks from build configuration (the root's
  `agent_framework_meta` is not its public API), or substitute a private implementation module.
  Packages without a bridge use their documented public top-level entry points. The explicit exceptions are
  `agent_framework_azure_cosmos_memory`, `agent_framework_azure_documentdb`, `agent_framework_duckdb`,
  `agent_framework_hosting`, `agent_framework_hosting_a2a`, `agent_framework_hosting_mcp`,
  `agent_framework_hosting_responses`, `agent_framework_hosting_telegram`, `agent_framework_mongodb`,
  `agent_framework_nvidia`, `agent_framework_oracle`, `agent_framework_postgres`, `agent_framework_qdrant`,
  `agent_framework_sql_server`, and `agent_framework_typesafe`. See their package READMEs and exported `__all__`;
  the inventory test checks each selected public export. A new exception must also be reviewed in the consumer
  allowlist before release.

From the repository root, check the generated file against the same base:

```bash
uv run --directory python --group tool-runtime python -m scripts.prepare_release --check --base-ref "$RELEASE_BASE" --tag "$RELEASE_TAG"
```

For version increases of existing distributions or an explicit manifest change, PR CI requires exactly one new
per-tag manifest and enforces agreement between its filename, JSON tag, and version changes. Ordinary development
PRs that only add new distribution identities do not need to choose a release tag or add a manifest. Explicit
release preparation still includes all selected new packages, and a supplied manifest is always validated.
Changes or deletions of historical manifests fail the check. Earlier files remain browsable on `main`;
their old package versions are not revalidated against current metadata. PRs without version or manifest changes
(including dependency maintenance) do not need to add a manifest. These files record reviewed intended batches,
not proof that publication completed; that evidence is the verified artifact manifest on the published release.

```bash
uv run --directory python --group tool-runtime poe validate-python-release --base-ref "$RELEASE_BASE"
```

Use the same freshly fetched main ref that the release branch was based on (`upstream/main` above; use `origin/main`
when that is the authoritative release base). Must exit 0. This task first regenerates `uv.lock`, then discovers the
package `pyproject.toml` files changed from that base and runs their published runtime dependencies and
non-development extras through lock-independent `lowest-direct` and `highest` import probes. The probes run in
parallel, derive the minimum supported Python minor from each package's internal editable closure, and share a hard
300-second deadline. Use `--python` only when the release requires an explicit interpreter override.

This is the release safety net for selective bumping: the lower probe catches unresolvable or unimportable external
floors, internal constraints that reject co-released package versions, and the upper probe catches caps that exclude
an installable package set. The JSON report records the concrete versions resolved in both scenarios. It does not
replace the package-by-package code inspection required by the strict core-floor policy. If it fails, fix the named
package/bound and re-run before committing.

Do not substitute the workspace-wide `validate-dependency-bounds-test` command here. That command runs every
package's full tests and Pyright in separate isolated environments and is intentionally reserved for CI or an
explicit dependency-range audit. The `Dependency Bounds Validation` check in `python-dependency-bounds.yml` runs that
full matrix for version-bump and new-workspace-package PRs and merge groups, while ordinary PRs skip it.
The bounded local release probes remain separate and do not replace that regression coverage.
If the release itself changes an external dependency range, also run
`validate-dependency-bounds-project --mode both --package <pkg> --dependency <name>` for that dependency.

If only prereleases changed (no `core` bump, no floor changes), release validation is still required because the
lockfile and both ends of each changed package's published dependency metadata must remain installable.

### 8. Commit (expect hook retry)

The project's pre-commit hook runs `poe check` / `poe typing` / `uv lock` and may re-modify `uv.lock` on first commit attempt. Expected pattern — run twice:

```bash
git add -u
git add "python/.github/release-${RELEASE_TAG}.json"  # New files are not included by git add -u.
git commit -m "<message>"   # may fail with "files were modified by this hook"
git add -u                  # re-stage hook-generated changes
git commit -m "<message>"   # succeeds
```

**Commit message format** — HEREDOC, no `Co-Authored-By`:

```bash
git commit -m "$(cat <<'EOF'
Bump Python package versions for <release-label> release

<One paragraph explaining:
 - which packages bumped and why (CHANGELOG-driven)
 - semver rationale for any released-tier bumps
 - whether a beta cohort bump was applied
 - whether core floors were raised, and under which policy>
EOF
)"
```

### 9. Push and report

```bash
git push origin bump-py-ver-release-YYMMDD
```

The push output includes a `Create a pull request for '<branch>' on GitHub by visiting: <URL>` line — surface that to the user.

### 10. Maintainer handoff: tag and existing draft (only when authorized)

After the reviewed bump PR merges, the maintainer selects the exact merged commit and creates the **one** overall
tag matching its `python/.github/release-<fulltag>.json`. The maintainer creates a GitHub **draft** release for that tag, with the
human-written title, complete release notes, and intended prerelease flag. Do not use a published release as the
trigger and do not create per-package tags. Release notes must be complete **before ESRP approval**; do not edit
the draft, tag, or selected source while a release run is in progress.

Azure DevOps discovery polls eligible existing drafts and tags. It has a disabled-by-default activation switch,
an explicit first eligible release ID, and durable claims on one retained ADO ledger run. A shared exclusive-lock
environment serializes discovery, authorization and finalization to admit one run for the whole batch. No Azure
storage account is needed. No GitHub workflow calls or queues Azure DevOps.

The protected pipeline reads `python/.github/release-<fulltag>.json` from the exact tagged commit, validates the requested names,
versions and tag, builds once, and runs isolated install/public-import checks against the selected artifacts.
It then waits for protected ESRP approval/publication and verifies the published distributions. Only after that
verification does it upload the **same built wheels/sdists and artifact manifest** to the **existing draft**,
verify those assets, and change `draft` to `false`. It preserves the draft's title, body, and prerelease flag.
The source request (`python/.github/release-<fulltag>.json`) and the output artifact manifest (file names, versions, sizes/checksums and
source provenance) are different records.

The published-event GitHub workflow validates the tag contract only. It must not build new artifacts, upload
release assets, publish packages, or request Azure DevOps credentials.

### Failure and recovery

- Before approval/publication: leave the draft unpublished, inspect the failing checks, and fix the source in a
  reviewed PR if needed. Do not move an existing release tag or silently replace its manifest. A new release
  attempt requiring source changes needs a new overall tag and appropriate new package versions.
- A queued/failed batch remains claimed. Use the consumer's audited recovery procedure to retry/reconcile the
  **same batch and retained artifact set**. Do not delete a claim to create parallel runs, queue individual
  distributions, or bypass the approval gate with local `uv publish`/Twine.
- Publication may partially succeed before a failure. PyPI versions are immutable: inspect package versions,
  retained artifact hashes, and the publication record before retrying. Already-published versions do not change
  the reviewed selection. Never overwrite or rebuild artifacts and assume they are identical.
- If publication succeeds but GitHub asset upload or finalization fails, keep the draft unpublished and retry
  that finalization using the verified retained artifacts. Do not republish packages, create a replacement
  release, or lose the human-authored release metadata.

### Rollout order (no publication as part of implementation)

1. Merge the Azure DevOps consumer first, with discovery disabled. Review the matching contract, artifact
   verification, recovery, and draft-only finalization.
2. Merge this repository's producer and retirement of the old GitHub build/upload path second.
3. Reuse the existing Azure DevOps GitHub service connection `github-agent-framework`, already used by the .NET
   release pipeline, and authorize it for the Python pipelines. Verify its repository and release access; do not
   introduce a separate GitHub App, private key, or Key Vault token-minting setup. Configure the shared
   `agent-framework-python-coordination` environment with an exclusive-lock check, initialize a retained discovery
   run with `initializeLedger: true`, and set its `releaseLedgerRunId` in both ADO pipelines. Keep ledger and release
   runs retained indefinitely. Verify the Build Service permissions and protected ESRP approval gates outside GitHub.
   No separate Azure storage identity is needed. Verify the merged upstream revision is compatible. Reusing the
   connection does not authorize a new pipeline automatically.
4. Choose the first eligible draft release ID and activate tag/draft discovery **last**, only after the previous
   steps are confirmed. Do not create production tags/drafts merely to test rollout.

The coordinated change requires both PRs and maintainer approval. Merging producer code alone must not enable
a second publisher or silently activate discovery.

Connection reuse does not mean reusing a release task that rewrites metadata or replaces existing assets.
The consumer's asset-only REST finalizer must still preserve the existing draft's title, body, and prerelease flag,
verify the exact retained artifacts, and publish only after verification. GitHub never receives Azure DevOps
credentials or queue permission.

## Pitfalls from past cycles — avoid repeating

- **Scoping from the wrong tag.** A release may have been tagged between bump cycles. Always compute `LAST_RELEASED_TAG` fresh — do NOT reuse the previous compare base. Symptom: dragging already-shipped PRs into the new CHANGELOG section.
- **Bumping packages that had no changes.** This was the old lockstep default. Now: a package without a CHANGELOG entry does not bump. The two exceptions (root follows core, optional beta cohort bump) are explicit choices, not defaults.
- **Touched package missing from CHANGELOG.** The inverse failure mode of the previous pitfall, and the dangerous one. If a PR landed code into `python/packages/foo/` but the new CHANGELOG section has no `**agent-framework-foo**:` line, then `foo` will NOT bump, and the fix sits in `main` but never reaches PyPI. Always run the touched-vs-mentioned reconciliation in step 4a before applying bumps.
- **Directory name vs PyPI name confusion.** Some package dirs use underscores or split names that differ from the published PyPI name (e.g. `foundry_local` → `agent-framework-foundry-local`). When reconciling touched dirs against CHANGELOG mentions, normalize on the PyPI form.
- **Forgetting root when core bumps.** Root `agent-framework` has `agent-framework-core[all]==EXACT_VERSION`. If `core` bumps and root does not, the pin is broken. Always bump them together and update the pin string.
- **Renaming an existing section header.** When drafting a new release, do NOT rewrite an existing `## [X.Y.Z]` header to a new label — that wipes the historical section. Always INSERT a new section above.
- **Forgetting footer reference links.** When a released-tier bump is in play, the `[Unreleased]` line and the new `[X.Y.Z]` link at the bottom MUST be updated. Heading links don't resolve without them.
- **Wrong footer compare base.** The new `[X.Y.Z]` line compares from the PREVIOUS released tag, not from two releases ago.
- **Timezone drift.** For alpha/beta date stamps, follow the `python-package-management` date-stamp rule;
  do not infer a local timezone from the user's current shell.
- **`Co-Authored-By` trailer.** Never add it. Rewrite/amend if it slipped in.
- **Stale inventory in this skill.** Always read `python/PACKAGE_STATUS.md` for the live tier map. Do not trust a hardcoded list.
- **Divergent origin vs upstream.** In fork clones, use freshly fetched `upstream/main` consistently for branch creation, changeset discovery, and release validation. A stale `origin/main` must never become the implicit compare base.
- **`--pre` README cleanup on promotion.** When a package is promoted to `released` in this cycle, grep for `pip install agent-framework-<pkg> --pre` in READMEs and drop the `--pre` flag.
- **RC counter inflation.** Do not increment `1.0.0rcN` without a CHANGELOG entry for that package. The counter tracks iterations, not calendar.

## References

- Package lifecycle and versioning source of truth: `python/.github/skills/python-package-management/SKILL.md`
- Lifecycle source of truth: `python/PACKAGE_STATUS.md`
- Release validator: `python/scripts/dependencies/validate_dependency_bounds.py --mode release` (changed-package,
  lock-independent `lowest-direct` and `highest` import probes under a five-minute deadline)
- Batch generator and read-only validator: `python/scripts/prepare_release.py`
- Read-only PR/published-tag check: `.github/workflows/python-release.yml`
- Poe task definitions: `python/pyproject.toml` `[tool.poe.tasks]`
