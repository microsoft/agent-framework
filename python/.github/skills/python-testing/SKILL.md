---
name: python-testing
description: >
  Guidelines for writing and running tests in the Agent Framework Python
  codebase. Use this when creating, modifying, or running tests.
---

# Python Testing

CI enforces at least 85% line coverage for every package classified Beta or Production/Stable.
Alpha packages are report-only, and the DevUI and experimental Lab packages are excluded from
aggregate coverage enforcement. Tests should be fast, reliable, and maintainable.
Test observable behavior first, and use coverage as a backstop. Meaningful new branches, error paths,
and edge cases must be covered without coupling tests to implementation details.
Before writing new tests, inspect the existing tests and coverage for the affected behavior. For refactors and
behavior-preserving implementation changes, update existing tests when they already express the contract. Add new
tests for new behavior, regressions, or a meaningful coverage gap rather than by default for every production edit.
We run tests in two stages, for a PR each commit is tested with unit tests only (using `-m "not integration"`), and the full suite including integration tests is run when merging.

When an API is marked as deprecated, migrate ordinary tests to its replacement in the same change. Retain only
focused tests that validate the deprecated behavior and warning; integration tests, samples, and unrelated unit
tests should use the supported API.

## Running Tests

```bash
# Run tests for all packages in parallel
uv run poe test

# Run tests for a specific workspace package
uv run poe test -P core

# Run all selected tests in a single pytest invocation
uv run poe test -A

# With coverage
uv run poe test -A -C
uv run poe test -P core -C

# Run only unit tests (exclude integration tests)
uv run poe test -A -m "not integration"

# Run only integration tests
uv run poe test -A -m integration
```

Direct package execution still works when you need it:

```bash
uv run --directory packages/core poe test
```

## Test Configuration

- **Async mode**: `asyncio_mode = "auto"` is enabled — do NOT use `@pytest.mark.asyncio`, but do mark tests with `async def` and use `await` for async calls
- **Timeout**: Default 60 seconds per test
- **Import mode**: `importlib` for cross-package isolation
- **Parallelization**: Large packages (core, ag-ui, orchestrations, anthropic) use `pytest-xdist` (`-n auto --dist worksteal`) in their `poe test` task. The aggregate `uv run poe test -A` sweep also uses xdist across the selected packages.

## Test Directory Structure

Test directories must NOT contain `__init__.py` files.

Non-core packages must place tests in a uniquely-named subdirectory:

```
packages/anthropic/
├── tests/
│   └── anthropic/       # Unique subdirectory matching package name
│       ├── conftest.py
│       └── test_client.py
```

Core package can use `tests/` directly with topic subdirectories:

```
packages/core/
├── tests/
│   ├── conftest.py
│   ├── core/
│   │   └── test_agents.py
│   └── openai/
│       └── test_client.py
```

## Fixture Guidelines

- Use `conftest.py` for shared fixtures within a test directory
- Before adding new fixtures, check if existing ones can be reused or extended
- For reusable setup that needs call-time parameters, use a fixture that returns a callable factory
- Consume fixtures through pytest injection; do not import fixtures or helpers from `conftest.py`
- Put non-fixture helpers in a normal helper module and import them explicitly
- Use descriptive names: `mapper`, `test_request`, `mock_client`

## File Naming

- Files starting with `test_` are test files — do not use this prefix for helpers
- Prefer extending an existing test file that already covers the same component or behavior; create a new file only for a distinct surface without an appropriate existing file
- Use `conftest.py` for shared fixtures and normal helper modules for other shared utilities

## Integration Tests

Integration tests require external services (OpenAI, Azure, etc.) and must be selectable and safely skippable:

1. **`@pytest.mark.integration`** — used for test selection, so integration tests can be included/excluded with `-m integration` / `-m "not integration"`
2. **`@skip_if_..._integration_tests_disabled`** decorator — skips the test when the required API keys or service endpoints are missing
3. **`@pytest.mark.flaky`** — add this only when the test is genuinely nondeterministic or service-sensitive

### Adding New Integration Tests

Every new integration test must have the integration marker and provider-specific skip condition. Add the flaky
marker when the scenario depends on timing, eventual consistency, a nondeterministic model response, or another
service-sensitive condition:

```python
@pytest.mark.flaky
@pytest.mark.integration
@skip_if_openai_integration_tests_disabled
async def test_openai_chat_completion() -> None:
    ...
```

For test files where all tests are integration tests (e.g., Azure Functions, Durable Task), use the module-level `pytestmark` list:

```python
pytestmark = [
    pytest.mark.flaky,
    pytest.mark.integration,
    pytest.mark.sample("01_single_agent"),
    pytest.mark.usefixtures("function_app_for_test"),
]
```

### CI Workflow

The merge CI workflow (`python-merge-tests.yml`) splits integration tests into parallel jobs by provider with change-based detection:

- **Unit tests** — always run all non-integration tests
- **OpenAI integration** — runs when `packages/core/agent_framework/openai/` or core infrastructure changes
- **Azure OpenAI integration** — runs when `packages/core/agent_framework/azure/` or core changes
- **Misc integration** — Anthropic, Ollama, MCP tests; runs when their packages or core change
- **Functions integration** — Azure Functions + Durable Task; runs when their packages or core change
- **Foundry integration** — runs when `packages/foundry/` or core changes

Core infrastructure changes (e.g., `_agents.py`, `_types.py`) trigger all integration test jobs. Scheduled and manual runs always execute all jobs.

### Keeping CI Workflows in Sync

Two workflow files define the same set of parallel test jobs:

- **`python-merge-tests.yml`** — runs on PRs, merge queue, schedule, and manual dispatch. Uses path-based change detection to skip unaffected integration jobs.
- **`python-integration-tests.yml`** — called from the manual integration test orchestrator (`integration-tests-manual.yml`). Always runs all jobs (no path filtering).

These workflows must be kept in sync. When you add, remove, or modify a test job, update **both** files. The job structure, pytest commands, and xdist flags should match between them. The only difference is that `python-merge-tests.yml` has path filters and conditional job execution, while `python-integration-tests.yml` does not.

### Updating the CI When Adding Integration Tests for a New Provider

When adding integration tests for a new provider package, you must update **both** `python-merge-tests.yml` and `python-integration-tests.yml`:

1. **Add a path filter** for the new provider in the `paths-filter` job in `python-merge-tests.yml` so the CI knows which file changes should trigger those tests.
2. **Add the test job to both workflow files** — either add them to the existing `python-tests-misc-integration` job, or create a dedicated job if the provider:
   - Has a large number of integration tests
   - Requires special infrastructure setup (emulators, Docker containers, etc.)
   - Has long-running tests that would slow down the misc job

The `python-tests-misc-integration` job is intended for small integration test suites that don't need dedicated infrastructure. When a provider's integration tests grow large or gain special requirements, split them out into their own job (like `python-tests-functions` was split out for Azure Functions + Durable Task).

## Best Practices

- Run only related tests, not the entire suite
- Review existing tests to understand coding style before creating new ones
- Test through the public or observable contract
- Mock external boundaries rather than the internal unit whose behavior the test should prove
- Use print statements for debugging, then remove them when done
- Resolve all errors and warnings before committing
