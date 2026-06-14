---
name: agent-framework-py-release
description: Use when cutting a Python release for the microsoft/agent-framework monorepo. Triggers on "bump py versions", "cut a python release", "prepare release PR for python", "release py packages", "bump python to X.Y.Z", or similar requests to bump Python package versions and prepare a release PR. Handles all four lifecycle tiers (alpha, beta, rc, released) with CHANGELOG-driven selective bumps, floor bound checks, and post-bump validation.
---

# Agent Framework Python Release

Cuts a Python release PR for the `microsoft/agent-framework` monorepo.

## Core principle: CHANGELOG drives bumps

**No more universal lockstep.** A package only bumps if it has a CHANGELOG entry this cycle. Draft the CHANGELOG first, then derive the bump list from it.

Exceptions to selective bumping (these stay coupled regardless of per-package changes):

- **Root `agent-framework` is coupled to `agent-framework-core` via `agent-framework-core[all]==X.Y.Z`** (exact pin in `python/pyproject.toml`). If `core` bumps, root bumps. Root may also bump independently for its own changes (docs/metadata/extras).
- **Beta-tier cohort bumps are still allowed** when the user explicitly wants a fresh date stamp across all betas for cohort signaling — but this is a deliberate user decision per release, not a default.

If the user explicitly states which packages to bump (or hands over a PR list per package), treat that as authoritative.

## Lifecycle tiers and version rules

Derive the live tier map at release time from `python/PACKAGE_STATUS.md` and the actual `version =` lines in each `pyproject.toml`. Do not hardcode counts — packages move between tiers. The current shape (as of 2026-05):

| Tier | Pattern | Bump rule |
| --- | --- | --- |
| `alpha` | `1.0.0aYYMMDD` | New Pacific date stamp on each bump. `.postN` suffix for same-day re-cuts. |
| `beta` | `1.0.0bYYMMDD` | Same as alpha. |
| `rc` | `1.0.0rcN` | Increment `N` only when the package has changes this cycle. Do NOT increment on date alone. |
| `released` | `X.Y.Z` | Apply semver **per package**: PATCH for bugfix only, MINOR for any new public API, MAJOR for breaking. |

Date stamp default: **current Pacific (US west coast) date**, not user's local Asia clock, not UTC. Same Pacific day re-cuts use `.postN`. Honor explicit user instruction over this default.

## Inputs to confirm before bumping

1. **The changeset**: explicit commits/PRs the release covers, OR derive from `git log ${LAST_RELEASED_TAG}..origin/main -- python/`.
2. **Per-package CHANGELOG entries**: which packages will get a line in the new release section. This list IS the bump list.
3. **Per-released-package semver bump**: for each released-tier package that has a CHANGELOG entry, decide PATCH / MINOR / MAJOR.
4. **Date stamp** (only if any alpha/beta is being bumped): default to Pacific YYMMDD.
5. **Optional cohort bump?**: ask if betas should all get a new date stamp regardless of per-package changes. Default: no.

If the user states target versions or a date explicitly, use exactly what they said — do not "correct" based on historical timezones.

## Non-negotiable rules

- **CHANGELOG-driven bumps**: only packages mentioned in the new CHANGELOG section get version bumps. Exceptions: root follows core (==pin); user-opted cohort bump on betas.
- **Preserve `gemini`'s `<2.0` cosmetic upper bound** — don't rewrite it to `<2` when touching its floor.
- **No `Co-Authored-By` trailer** on any commit.
- **Use `uv run`** for all Python/poe commands (`uv run poe ...`, `uv run pytest ...`).
- **Never rename an existing CHANGELOG section header** during a new release cut. Only INSERT a new section above existing ones.
- **Footer reference links are part of the CHANGELOG edit**, not optional.

## Workflow

### 1. Orient and create branch

```bash
git fetch origin main --tags --quiet
git fetch upstream main --tags --quiet 2>/dev/null || true
git status
```

If the user already has a `bump-py-ver-release-*` branch checked out, use it. Otherwise:

```bash
git checkout -b bump-py-ver-release-YYMMDD origin/main
```

### 2. Build the live tier map

Read `python/PACKAGE_STATUS.md` to enumerate current packages and lifecycle stages, and `grep '^version' python/pyproject.toml python/packages/*/pyproject.toml` to confirm actual versions. Cross-reference — if `PACKAGE_STATUS.md` shows a package as `beta` but its version looks like `1.0.0aYYMMDD`, surface the inconsistency before proceeding.

Watch for: new packages added since the last release, lifecycle transitions (alpha→beta, beta→rc, rc→released), and stale packages that haven't been touched in many cycles.

### 3. Identify changeset

Use the LATEST released tag as the compare base:

```bash
LAST_RELEASED_TAG=$(
  git tag -l 'python-[0-9]*.[0-9]*.[0-9]*' \
    | uv run --directory python python -c 'import sys; tags=[t.strip() for t in sys.stdin if t.strip()]; print(max(tags, key=lambda t: tuple(map(int, t[7:].split(".")))))'
)
echo "Compare base: $LAST_RELEASED_TAG"
```

List commits and packages touched:

```bash
git log --oneline ${LAST_RELEASED_TAG}..origin/main -- python/ ':!python/CHANGELOG.md'

# Per-commit package footprint
for sha in $(git log --format='%H' ${LAST_RELEASED_TAG}..origin/main -- python/); do
  echo "--- $(git show -s --format='%h %s' $sha) ---"
  git show --name-only --format='' $sha | grep '^python/packages/' | \
    sed 's|^python/packages/||' | awk -F/ '{print $1}' | sort -u
done
```

If the release ultimately tags from `upstream/main` but `origin/main` is behind, also run:

```bash
git log --oneline ${LAST_RELEASED_TAG}..upstream/main -- python/ ':!python/CHANGELOG.md'
```

If user provides an explicit commit/PR list, treat THAT as authoritative.

#### 3a. Build the authoritative touched-package set

Aggregate the per-commit footprint into a single union across the whole range. This is the **source of truth** for what must appear in the CHANGELOG. Save it before drafting entries.

```bash
# Union of all touched package directories across the range
git log --name-only --format='' ${LAST_RELEASED_TAG}..origin/main -- python/packages/ \
  | grep '^python/packages/' \
  | sed 's|^python/packages/||' \
  | awk -F/ '{print $1}' \
  | sort -u

# Root-level files (drive a root agent-framework entry if substantive)
git log --name-only --format='' ${LAST_RELEASED_TAG}..origin/main \
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
TOUCHED_PACKAGES=$(git log --name-only --format='' ${LAST_RELEASED_TAG}..origin/main -- python/packages/ \
  | grep '^python/packages/' \
  | sed 's|^python/packages/||' \
  | awk -F/ '{print $1}' \
  | sort -u)

ROOT_TOUCHED=$(git log --name-only --format='' ${LAST_RELEASED_TAG}..origin/main \
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

### 6. Floor bound updates on `agent-framework-core`

Only relevant when `core` itself bumped this cycle. Two policies, pick one explicitly with the user:

- **Conservative (default)**: raise `agent-framework-core>=X.Y.Z` to the new core version on every non-core package that is ALSO bumping this cycle. Leaves packages-not-bumped at their existing floor.
- **Strict per-upstream-doc**: only raise the floor on packages that actually consume a new core API introduced in the bump. This requires per-package code inspection. Use only when the user is comfortable letting `validate-dependency-bounds-test` (lower-resolution pass) catch any mistakes.

Preserve `gemini`'s `<2.0` cosmetic upper bound — replace ONLY the `>=OLD` half:

```bash
file="python/packages/<pkg>/pyproject.toml"
sed -i.bak "s/agent-framework-core>=${OLD_CORE}/agent-framework-core>=${NEW_CORE}/" "$file"
rm "${file}.bak"
```

If `core` did not bump this cycle, do not touch floors.

### 7. Validate

```bash
cd python && uv run poe validate-dependency-bounds-test
```

Must exit 0. This is the safety net for selective bumping: the lower-resolution pass catches floors set too low for code that depends on new APIs, and the upper pass catches caps that exclude installable versions. If it fails, the output names the offending bound — fix and re-run before committing. This step also regenerates `uv.lock` to match new bounds.

If only prereleases changed (no `core` bump, no floor changes), this validation is still required — `uv.lock` regeneration alone justifies the run.

### 8. Commit (expect hook retry)

The project's pre-commit hook runs `poe check` / `poe typing` / `uv lock` and may re-modify `uv.lock` on first commit attempt. Expected pattern — run twice:

```bash
git add -u
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

## Pitfalls from past cycles — avoid repeating

- **Scoping from the wrong tag.** A release may have been tagged between bump cycles. Always compute `LAST_RELEASED_TAG` fresh — do NOT reuse the previous compare base. Symptom: dragging already-shipped PRs into the new CHANGELOG section.
- **Bumping packages that had no changes.** This was the old lockstep default. Now: a package without a CHANGELOG entry does not bump. The two exceptions (root follows core, optional beta cohort bump) are explicit choices, not defaults.
- **Touched package missing from CHANGELOG.** The inverse failure mode of the previous pitfall, and the dangerous one. If a PR landed code into `python/packages/foo/` but the new CHANGELOG section has no `**agent-framework-foo**:` line, then `foo` will NOT bump, and the fix sits in `main` but never reaches PyPI. Always run the touched-vs-mentioned reconciliation in step 4a before applying bumps.
- **Directory name vs PyPI name confusion.** Some package dirs use underscores or split names that differ from the published PyPI name (e.g. `foundry_local` → `agent-framework-foundry-local`). When reconciling touched dirs against CHANGELOG mentions, normalize on the PyPI form.
- **Forgetting root when core bumps.** Root `agent-framework` has `agent-framework-core[all]==EXACT_VERSION`. If `core` bumps and root does not, the pin is broken. Always bump them together and update the pin string.
- **Renaming an existing section header.** When drafting a new release, do NOT rewrite an existing `## [X.Y.Z]` header to a new label — that wipes the historical section. Always INSERT a new section above.
- **Forgetting footer reference links.** When a released-tier bump is in play, the `[Unreleased]` line and the new `[X.Y.Z]` link at the bottom MUST be updated. Heading links don't resolve without them.
- **Wrong footer compare base.** The new `[X.Y.Z]` line compares from the PREVIOUS released tag, not from two releases ago.
- **Timezone drift.** Prerelease date stamp follows the current Pacific date — NOT user's local Asia clock, NOT UTC. Same-Pacific-day re-cuts use a `.postN` suffix.
- **`Co-Authored-By` trailer.** Never add it. Rewrite/amend if it slipped in.
- **Stale inventory in this skill.** Always read `python/PACKAGE_STATUS.md` for the live tier map. Do not trust a hardcoded list.
- **`gemini`'s `<2.0` upper bound.** When touching its floor, do not rewrite `<2.0` to `<2`.
- **Divergent origin vs upstream.** If the release tags from `upstream/main` but `origin/main` is behind, check both — warn if they differ and offer to sync.
- **`--pre` README cleanup on promotion.** When a package is promoted to `released` in this cycle, grep for `pip install agent-framework-<pkg> --pre` in READMEs and drop the `--pre` flag.
- **RC counter inflation.** Do not increment `1.0.0rcN` without a CHANGELOG entry for that package. The counter tracks iterations, not calendar.

## References

- Upstream canonical skill (in-repo): `python/.github/skills/python-package-management/SKILL.md`
- Lifecycle source of truth: `python/PACKAGE_STATUS.md`
- Validator: `python/scripts/dependencies/validate_dependency_bounds.py` (runs `lowest-direct` and `highest` resolution smoke tests; catches floors/caps that don't match the code)
- Poe task definitions: `python/pyproject.toml` `[tool.poe.tasks]`
