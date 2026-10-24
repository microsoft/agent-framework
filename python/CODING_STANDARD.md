# Python Coding Standards

This document is the canonical source for Python coding standards in Agent Framework.
It applies to package source, tests, samples, and Python-specific repository tooling under `python/`.

Exact formatter, linter, and type-checker settings live in the relevant configuration files. This document explains
the engineering intent behind those settings and defines the rules that require design judgment.

## Requirement Levels

- **MUST** and **MUST NOT** define requirements.
- **SHOULD** and **SHOULD NOT** define the expected default. Deviations require a concrete reason.
- **MAY** identifies an acceptable option, not a preference.

New code and materially edited code MUST follow these standards. Existing code may not yet conform everywhere; do not
copy a non-conforming pattern merely because it already exists.

## Engineering Priorities

When principles compete, use this order:

1. Correctness and public API clarity
2. Maintainability and readability
3. Measured performance
4. Typing purity

- Code MUST preserve public compatibility unless a breaking change has been explicitly approved and documented.
  Do not invent compatibility aliases or shims without that decision.
- Code SHOULD use the most explicit, unsurprising implementation with the clearest data flow, even when it is slightly
  more verbose.
- Inputs from users, external services, files, environment variables, and other trust boundaries MUST be validated.
  Inside trusted typed code, rely on documented invariants and fail at the point where an invariant is broken.
- Mutation MUST be intentional and visible in the API. Accept read-only abstractions when mutation is unnecessary,
  and do not make defensive copies without a concrete ownership or correctness need.
- A new abstraction SHOULD centralize meaningful policy, remove real duplication, or create a stable boundary.
  Do not add speculative abstractions or wrappers whose only purpose is satisfying a type checker.

## Tool-Enforced Style

Ruff is the formatter and linter. The current configuration uses a 120-character line length and targets Python 3.10
or later. `pyproject.toml` and the other tool configuration files are the source of truth for exact values and enabled
rules.

- Every checked-in `.py` file MUST start with:

  ```python
  # Copyright (c) Microsoft. All rights reserved.
  ```

- Code MUST NOT shadow Python built-ins. A compatibility exception requires an explicit API decision.
- Package source files that are new or materially edited MUST use:

  ```python
  from __future__ import annotations
  ```

- `TypeVar` names MUST use a descriptive `T` suffix.

  ```python
  # Preferred
  ChatResponseT = TypeVar("ChatResponseT", bound=ChatResponse)

  # Avoid
  TChatResponse = TypeVar("TChatResponse", bound=ChatResponse)
  ```

Purely mechanical findings that the required formatter, linter, or type checkers already report should be fixed through
those tools rather than duplicated as subjective review guidance.

## Type Annotations

Typing is a design aid, not an end in itself.

- Public APIs MUST have complete, stable parameter and return annotations.
- Functions and methods in package source MUST annotate every parameter and return value. A trivially inferred local
  callable, such as a short lambda or nested callback, MAY rely on inference.
- Tests and samples follow their configured relaxed checker profiles; complete annotations are not universally
  required there. Add annotations when they clarify reusable helpers, fixtures, callbacks, or copied public usage.
- Package source MUST pass the configured strict Pyright checks.
- Tests MUST pass the repository-configured Pyright, mypy, pyrefly, ty, and zuban profiles.
- Samples MUST pass the configured supported subset of those checkers.
- The exact checker responsibilities and commands live in
  [`python-code-quality`](.github/skills/python-code-quality/SKILL.md).

### Collection Inputs

Input parameters that do not mutate a collection SHOULD use the narrowest practical read-only abstraction, such as
`Mapping`, `Sequence`, or `Collection`, instead of requiring a mutable concrete type.

```python
# Preferred
def process_config(config: Mapping[str, Any]) -> None:
    ...


# Avoid when mutation is not required
def process_config(config: MutableMapping[str, Any]) -> None:
    ...
```

### Suppressions and Casts

Resolve type-checker failures in this order:

1. Improve the annotations, protocol, overload, or design.
2. Use a narrow, rule-specific suppression when the checker cannot represent a valid runtime contract.
3. Use `cast()` only when it materially improves clarity.
4. Add a runtime check only when runtime validation is semantically required.

Additional rules:

- Source code SHOULD use a line-level, rule-specific `# pyright: ignore[...]` when a suppression is unavoidable.
- Internal implementation code MAY use a rule-specific `# type: ignore[...]` when it is clearer than
  checker-specific suppressions. The ignore MUST include a brief inline reason explaining the valid runtime contract
  or checker limitation.
- Tests and samples MUST use only the minimum checker-specific suppressions required by their configured profiles.
  A line MAY need both a Pyright suppression and a mypy-compatible suppression when the checkers report independent
  findings.
- File-level suppressions MUST be limited to generated code or a documented file-wide checker limitation that cannot
  be addressed locally.
- An Agent Framework package MAY intentionally use another Agent Framework package's private helper. Keep the helper
  private and use a targeted `reportPrivateUsage` suppression rather than making it public solely for the checker.
- Private members of third-party dependencies SHOULD NOT be used unless the integration has a documented, unavoidable
  reason.
- Code MUST NOT add trivial pass-through helpers or extra assignments solely to satisfy typing.

## Public API Design

Python APIs should keep the common path simple without removing advanced extensibility.

### Import-Light Common Paths

- A common operation SHOULD require one primary Agent Framework import for that concept.
- Simple configuration SHOULD use keyword-only parameters, plain Python values, or typed structural data rather than
  forcing callers to construct several framework-owned data-holder classes.
- Additional framework imports MAY be required for advanced behavior.
- A public configuration class SHOULD exist only when it owns meaningful validation or behavior, is independently
  reusable, or represents a durable domain concept. Do not create a class merely to group arguments for one call.
- Choose between keyword-only parameters and a `TypedDict` case by case. Prefer keyword-only parameters for direct
  discoverability. Prefer a `TypedDict` when the values form a cohesive payload that is passed, stored, or forwarded
  as data. There is no field-count cutoff.

`ChatOptions` is the preferred model for extensible structured options: common fields are typed without requiring
callers to instantiate a configuration object, provider-specific types can extend the structure, and generic APIs can
carry a caller- or provider-defined `TypedDict` without waiting for Agent Framework to add another public class.

- An API that expects users or providers to extend structured options SHOULD be generic over their `TypedDict` rather
  than requiring configuration-class inheritance.

### Function Signatures

- Positional parameters SHOULD be obvious, stable, and difficult to misorder. There is no fixed numeric limit.
- Optional or evolving parameters SHOULD be keyword-only.
- Public APIs SHOULD accept a string alternative to an enum or framework type when that makes the common path simpler
  and the string vocabulary is stable.
- String alternatives MUST use `Literal[...]` to enumerate supported values and MUST normalize to the canonical type
  at the API boundary.

```python
def create_agent(
    name: str,
    *,
    tool_mode: Literal["auto", "required", "none"] | ChatToolMode = "auto",
) -> Agent:
    if isinstance(tool_mode, str):
        tool_mode = ChatToolMode(tool_mode)
    ...
```

### Flexible Arguments

`**kwargs` is an escape route, not the default shape for known data.

- Known framework data MUST use explicit parameters.
- `**kwargs` MAY be used for documented subclass extensibility.
- `**kwargs` MAY be used for a narrow passthrough to a large or unstable external SDK surface.
- A flexible payload that is part of the API contract SHOULD use a purpose-named mapping such as
  `additional_properties`, `client_kwargs`, or `function_invocation_kwargs`.
- The API MUST document who owns the mapping, where it is forwarded, and whether values are copied or mutated.
- Wrappers MUST NOT accept or forward generic keyword arguments they do not use.

### Interfaces and Reuse

- Behavioral contracts SHOULD use `Protocol`.
- An abstract base class SHOULD be used only when inheritance provides shared implementation, lifecycle, construction
  control, or other required runtime semantics.
- Composition and inheritance are both acceptable. Choose based on substitutability, lifecycle, and clarity rather
  than a blanket preference.

## Asynchronous Code and Resource Ownership

- Use asynchronous APIs for I/O and concurrency. Keep purely synchronous work synchronous.
- Async code MUST NOT block the event loop with synchronous network, file, process, or long-running CPU work.
- Cancellation MUST propagate. Cleanup belongs in `finally` blocks or context managers; cancellation MUST NOT be
  translated into ordinary success or an unrelated framework exception.
- Resource ownership MUST be explicit:
  - Close or cancel resources the object creates.
  - Do not close caller-injected resources.
  - Use synchronous or asynchronous context managers when lifecycle management is part of correct use.

## Exception Hierarchy

The authoritative classes live in
[`packages/core/agent_framework/exceptions.py`](packages/core/agent_framework/exceptions.py). This document defines
how to choose and use them rather than duplicating a hierarchy that can drift.

- Broken internal invariants SHOULD fail immediately at the point of violation.
- Invalid Python arguments, configuration values, or object state SHOULD use built-in exceptions such as
  `TypeError`, `ValueError`, or `RuntimeError`.
- Domain failures that callers may handle distinctly MUST use the Agent Framework exception branch owned by that
  domain, such as Agent, ChatClient, Integration, Workflow, Tool, or Middleware.
- Exception selection MUST follow domain ownership rather than HTTP status code or a generic category alone.
- Translated exceptions MUST preserve their cause with `raise ... from exc`.
- Code MUST NOT silently swallow errors, return a success-shaped fallback after failure, or use a broad catch without
  an explicit recovery boundary.
- New exception names SHOULD follow the established naming convention of their domain. Do not force one universal
  `Error` or `Exception` suffix across all branches.
- Renames and removals MUST follow the general public compatibility policy. Do not assume either a clean break or a
  compatibility alias without an approved API decision.

Use the following selection guide:

| Scenario | Exception family |
|---|---|
| Invalid argument or configuration | Built-in `TypeError` or `ValueError` |
| Object in an invalid internal state | Built-in `RuntimeError` |
| Agent lookup or response handling failure | `AgentException` branch |
| Chat-provider request, response, auth, or filtering failure | `ChatClientException` branch |
| Non-chat external dependency failure | `IntegrationException` branch |
| Workflow execution or validation failure | `WorkflowException` branch |
| Tool execution failure | `ToolException` branch |

## Connector Conventions

### Settings Resolution

Connector constructors MUST use `load_settings` to resolve explicit keyword arguments, an explicitly selected `.env`
file, process environment variables, and defaults before deciding that a required value is missing.

When a preconfigured SDK client can be injected:

- The client and individual settings MAY both be omitted at the constructor boundary.
- Settings MUST become required only on the branch that constructs the SDK client.
- The constructor MUST NOT reject an injected client merely because optional credentials or model settings were also
  provided. The injected client owns its transport and authentication.

```python
settings = load_settings(
    ProviderSettings,
    env_prefix="PROVIDER_",
    required_fields=[] if client is not None else ["api_key"],
    api_key=api_key,
    env_file_path=env_file_path,
    env_file_encoding=env_file_encoding,
)

if client is None:
    client = ProviderClient(
        api_key=cast(SecretString, settings.get("api_key")).get_secret_value(),
    )
```

### Transformation Helper Names

Connector implementations SHOULD use these names when they accurately describe the operation:

- `_prepare_<object>_for_<purpose>` for data prepared for an external service.
- `_parse_<object>_from_<source>` for data received from an external service.

These are consistency patterns, not mandatory templates. Use a clearer verb when the operation has different
semantics.

## Imports and Public Exports

Consumer-facing documentation and samples MUST use stable public imports:

```python
from agent_framework import Agent, Message, tool
from agent_framework.observability import configure_otel_providers
from agent_framework.openai import OpenAIChatClient
```

Private defining modules remain implementation details.

- Wildcard imports are prohibited in production `.py` and `.pyi` files. Generated code MAY be explicitly exempted.
- Package and public import surfaces MUST define an explicit `__all__`.
- Internal modules SHOULD omit `__all__` unless the module intentionally defines a supported public import surface.
- Runtime `.py` re-exports SHOULD use direct imports without identity aliases.
- `.pyi` stubs SHOULD use identity aliases for re-exported names so type checkers recognize the public surface.

### Root Lazy Exports

When adding, removing, or moving a root `agent_framework` export, the change MUST:

1. Update `_LAZY_MODULE_EXPORTS` in `packages/core/agent_framework/__init__.py`.
2. Keep the derived lazy export registry and explicit runtime `__all__` synchronized.
3. Update `packages/core/agent_framework/__init__.pyi`.
4. Keep deprecation behavior in the owning module rather than adding symbol-specific branches to the root
   `__getattr__`.
5. Validate direct import and wildcard import behavior.

Package-governance decisions and detailed validation commands live in
[`python-package-management`](.github/skills/python-package-management/SKILL.md).

## Documentation

### Module Docstrings

- Every public module, including public `__init__.py` modules, MUST have a concise module docstring focused on its
  purpose.
- Namespace modules SHOULD NOT maintain long package or supported-symbol inventories in their docstrings.
- For a module with a docstring, the order MUST be:
  1. Copyright comment
  2. Optional top-level metadata comments, such as a PEP 723 block
  3. Module docstring
  4. `from __future__ import annotations`, when applicable
  5. Imports

### API Docstrings

Public APIs MUST use Google-style docstrings.

- The summary MUST use imperative mood and end with a period.
- Docstrings MUST explain behavior, constraints, meaningful errors, and non-obvious semantics rather than restating
  the signature.
- Positional and ordinary parameters belong under `Args:`.
- Keyword-only parameters belong under `Keyword Args:`.
- `Returns:` or `Yields:` SHOULD be present when the value has meaningful semantics beyond its annotation. Omit it
  for `None` and obvious trivial values.
- `Raises:` MUST document intentionally raised Agent Framework exceptions.
- `Raises:` SHOULD document built-in exceptions when callers can meaningfully act on a non-obvious condition.
- Examples SHOULD use an `Examples:` section with `.. code-block:: python`.
- Internal docstrings and comments SHOULD explain important intent, invariants, or tradeoffs. Do not narrate obvious
  code.

```python
def equal(arg1: str, arg2: str, *, case_sensitive: bool = True) -> bool:
    """Compare two strings.

    Args:
        arg1: The first string to compare.
        arg2: The second string to compare.

    Keyword Args:
        case_sensitive: Whether comparison preserves letter case.

    Returns:
        Whether the strings are equal under the selected comparison mode.
    """
    ...
```

## Logging and Telemetry

- Log actionable, structured context at the boundary that owns the failure or decision.
- Secrets, credentials, tokens, and sensitive user content MUST NOT be logged or emitted to telemetry by default.
- Exception logging SHOULD preserve the original exception and stack context.
- Logs SHOULD help an operator decide what failed and where; avoid duplicate logging at every layer of the same call.

## Performance and Serialization

- Code MUST avoid obvious repeated expensive work and redundant conversions.
- A less-readable micro-optimization SHOULD require measurement or a clearly established hot path.
- Caching SHOULD be introduced only for repeated expensive work with stable inputs and clear lifetime or invalidation
  semantics.
- Cached mutable values MUST have explicit ownership semantics so callers cannot corrupt shared cached state.
- Choose `isinstance()`, a discriminator such as `.type`, or structural matching based on semantics. Do not replace
  one with another solely because of a blanket performance claim.

When serializing:

- Compute a representation once and reuse it when several consumers need the same value.
- Use a known model's own `to_dict()` or equivalent when its exact type is known.
- Use the framework's optimized `make_json_safe()` converter for heterogeneous values containing framework models,
  Pydantic models, dataclasses, containers, or primitives.
- Keep provider-specific conversion local when an external API requires exact aliases, JSON modes, or opaque JSON
  strings.
- Avoid `json.dumps()` followed by `json.loads()` unless crossing a required wire-format boundary.

## Testing

Tests are behavior-first. Coverage is a backstop, not the objective.

- Tests MUST validate the public or observable contract rather than mirror implementation details.
- Meaningful new branches, error paths, and edge cases MUST be covered.
- Mocks SHOULD replace external boundaries, not the internal units whose behavior the test is meant to prove.
- Test names SHOULD describe the behavior and condition under test.

### Test Layout

- Test directories MUST NOT contain `__init__.py`.
- Files beginning with `test_` MUST contain tests; helper modules MUST use another name.
- Non-core packages MUST place tests under a uniquely named `tests/<package>/` directory.
- Core MAY use `packages/core/tests/` directly with topic subdirectories.
- Keep the package-level `tests/` directory even when tests live in a nested package-specific directory.

### Fixtures and Helpers

- Shared fixtures MUST live in `conftest.py`.
- Parameterized reusable setup SHOULD use a fixture that returns a callable factory.
- Fixtures MUST be consumed through pytest injection, not imported from `conftest.py`.
- Non-fixture helpers MUST live in a normal helper module and be imported explicitly.
- Fixture names SHOULD describe the provided value or capability, such as `client`, `test_request`, or
  `configured_agent`.

### Integration Tests

Every external-service integration test MUST have:

- `@pytest.mark.integration`
- A provider-specific skip condition for missing credentials, endpoints, or required infrastructure

Add `@pytest.mark.flaky` only when the test is genuinely nondeterministic or service-sensitive.

Task-specific commands, CI workflow synchronization, and integration-job placement live in
[`python-testing`](.github/skills/python-testing/SKILL.md).

## Related Guidance

- [Python development setup](DEV_SETUP.md)
- [Python testing skill](.github/skills/python-testing/SKILL.md)
- [Python code-quality skill](.github/skills/python-code-quality/SKILL.md)
- [Python package-management skill](.github/skills/python-package-management/SKILL.md)
- [Sample guidelines](samples/SAMPLE_GUIDELINES.md)
