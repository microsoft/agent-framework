# Copyright (c) Microsoft. All rights reserved.

---
name: python-feature-lifecycle
description: >
  Guidance for package and feature lifecycle in the Agent Framework Python
  codebase, including stage meanings, feature-stage decorators, feature enums,
  and how to move APIs from one stage to the next.
---

# Python Feature Lifecycle

## Two lifecycle levels

Agent Framework uses lifecycle at two different levels:

1. **Package lifecycle** — the maturity of the package as a whole
2. **Feature lifecycle** — the maturity of a specific API or feature inside that package

These are related, but they are **not the same thing**.

- The **package stage is the default** for everything in the package.
- **Feature-stage decorators are only for exceptions** when a feature is behind the package's default stage.
- Do **not** decorate every class or function just because the package is experimental or release candidate.

### Important default

If a package is still in **beta / experimental preview**, all public APIs in that package are experimental by default.

- Do **not** add `@experimental(...)` everywhere in that package.
- The package stage already communicates that default.

Once a package moves forward, you can keep individual features behind:

- If a package moves to **release candidate**, a feature may remain **experimental**
- If a package moves to **released / GA**, a feature may remain **experimental** or **release candidate**

That is the main use case for feature-stage decorators.

## The four stages

### 1. Experimental

Use for features that are still unstable and may change or be removed without notice.

Feature-level code pattern:

```python
from ._feature_stage import ExperimentalFeature, experimental


@experimental(feature_id=ExperimentalFeature.MY_FEATURE)
class MyFeature:
    ...
```

Behavior:

- Adds an experimental warning block to the docstring
- Records feature metadata on the decorated object
- Emits a runtime warning the first time the feature is used (once per feature by default)

Enum setup:

- Add an all-caps member to `ExperimentalFeature`
- Reuse the same feature ID across all APIs that belong to the same conceptual feature

### 2. Release candidate

Use for features that are nearly stable but may still receive small refinements before GA.

Feature-level code pattern:

```python
from ._feature_stage import ReleaseCandidateFeature, release_candidate


@release_candidate(feature_id=ReleaseCandidateFeature.MY_FEATURE)
class MyFeature:
    ...
```

Behavior:

- Adds a release-candidate note to the docstring
- Records feature metadata on the decorated object
- Does **not** emit the experimental warning

Enum setup:

- Add an all-caps member to `ReleaseCandidateFeature`

### 3. Released

Use for stable GA APIs.

Code pattern:

- **No feature-stage decorator**
- **No entry** in `ExperimentalFeature`
- **No entry** in `ReleaseCandidateFeature`

If a feature is fully released, remove any stage-specific feature annotation.

### 4. Deprecated

Use for APIs that still exist but should not be used for new code.

Code pattern:

```python
import sys

if sys.version_info >= (3, 13):
    from warnings import deprecated  # type: ignore # pragma: no cover
else:
    from typing_extensions import deprecated  # type: ignore # pragma: no cover


@deprecated("MyOldFeature is deprecated. Use MyNewFeature instead.")
class MyOldFeature:
    ...
```

Behavior:

- Uses the repository's version-conditional deprecation import pattern
- Should describe what to use instead

Deprecated APIs should not also carry feature-stage decorators.

## Expected decorators by stage

| Feature stage | Expected annotation |
| --- | --- |
| Experimental | `@experimental(feature_id=ExperimentalFeature.X)` |
| Release candidate | `@release_candidate(feature_id=ReleaseCandidateFeature.X)` |
| Released | No feature-stage decorator |
| Deprecated | `@deprecated("...")` |

## Feature enums

The feature enums are the inventory of currently staged features:

- `ExperimentalFeature`
- `ReleaseCandidateFeature`

Guidance:

- Use one enum member per conceptual feature, not per class
- Ideally, an ADR already defines the overall feature boundary and therefore the feature ID that staged APIs for that feature should reuse
- Keep feature IDs all caps
- Reuse the same member across related APIs for the same feature
- Remove enum members when the feature no longer belongs to that stage
- Treat these enums as **current-stage inventories**, not as a stable consumer introspection API

Minimal consumer guidance:

- Treat `__feature_stage__` and `__feature_id__` as optional staged metadata, not as stable contracts
- Use `getattr(obj, "__feature_stage__", None)` and `getattr(obj, "__feature_id__", None)` rather than direct attribute access
- Treat missing metadata as "no explicit feature-stage annotation"
- For warning filters while a feature is staged, match the literal feature ID string
- Do **not** rely on `ExperimentalFeature.X`, `ReleaseCandidateFeature.X`, or the continued presence of `__feature_id__` after a feature moves stages or is released

For consumers, the enums are also re-exported from `agent_framework`.

For internal implementation code inside `agent_framework`, continue to import the enums and decorators from `._feature_stage`.

## Package stage vs feature stage

Use the following rules:

### Package is experimental / beta

- All public APIs are experimental by default
- Do **not** add feature-stage decorators just to restate that
- Only introduce feature-level annotations later if the package advances first

### Package is release candidate

- All public APIs are RC by default
- Do **not** decorate everything
- Add `@experimental(...)` only for features that are intentionally still behind the package

### Package is released / GA

- All public APIs are released by default
- Add `@experimental(...)` or `@release_candidate(...)` only for features still being held back

## Moving a feature from one stage to the next

### Experimental -> Release candidate

1. Move the feature ID from `ExperimentalFeature` to `ReleaseCandidateFeature`
2. Replace `@experimental(...)` with `@release_candidate(...)`
3. Update any tests or docs that mention the old stage

### Experimental -> Released

1. Remove `@experimental(...)`
2. Remove the feature from `ExperimentalFeature`
3. Do not add a replacement feature-stage decorator

### Release candidate -> Released

1. Remove `@release_candidate(...)`
2. Remove the feature from `ReleaseCandidateFeature`
3. Leave the API undecorated

### Any stage -> Deprecated

1. Remove any feature-stage decorator
2. Remove the feature from the stage enum
3. Add `@deprecated("...")`
4. Update docs/tests to reflect the replacement path

## Promotion guidance

Features do **not** have to pass through every stage.

- It is usually a good idea to move features in order when that reflects reality
- But it is completely acceptable to go **experimental -> released**
- Do **not** force a feature through release candidate if there is no real RC period

Likewise, when a package advances, do not automatically move every feature with it.

- Promote features based on actual readiness
- Keep lagging features explicitly marked only when they are behind the package default

## Practical rules of thumb

- **Package default first, feature exceptions second**
- **Do not decorate everything in preview packages**
- **Do not double-annotate members of an already-staged class**
- **Use enums only for currently staged features**
- **Do not treat stage enums as a compatibility contract**
- **Treat `__feature_stage__` and `__feature_id__` as optional metadata; use `getattr`**
- **Remove stage annotations once a feature is released or deprecated**
