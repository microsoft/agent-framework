---
name: python-testing
description: >
  Guidelines for writing and running tests in the Agent Framework Python
  codebase. Use this when creating, modifying, or running tests.
---

# Python Testing

We strive for at least 85% test coverage across the codebase, with a focus on core packages and critical paths. Tests should be fast, reliable, and maintainable.
When adding new code, check that the relevant sections of the codebase are covered by tests, and add new tests as needed. When modifying existing code, update or add tests to cover the changes.
We run tests in two stages, for a PR each commit is tested with unit tests only (using `-m "not integration"`), and the full suite including integration tests is run when merging.

## Running Tests

```bash
# Run tests for all packages in parallel
uv run poe test

# Run tests for a specific package
uv run --directory packages/core poe test

# Run all tests in a single pytest invocation (faster, uses pytest-xdist)
uv run poe all-tests

# With coverage
uv run poe all-tests-cov

# Run only unit tests (exclude integration tests)
uv run poe all-tests -m "not integration"

# Run only integration tests
uv run poe all-tests -m integration
```

## Test Configuration

- **Async mode**: `asyncio_mode = "auto"` is enabled — do NOT use `@pytest.mark.asyncio`, but do mark tests with `async def` and use `await` for async calls
- **Timeout**: Default 60 seconds per test
- **Import mode**: `importlib` for cross-package isolation
- **Parallelization**: Large packages (core, ag-ui, orchestrations, anthropic) use `pytest-xdist` (`-n auto --dist worksteal`) in their `poe test` task. The `all-tests` task also uses xdist across all packages.

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
- Use descriptive names: `mapper`, `test_request`, `mock_client`

## File Naming

- Files starting with `test_` are test files — do not use this prefix for helpers
- Use `conftest.py` for shared utilities

## Integration Tests

Integration tests require external services (OpenAI, Azure, etc.) and are controlled by three markers:

1. **`@pytest.mark.flaky`** — marks the test as potentially flaky since it depends on external services
2. **`@pytest.mark.integration`** — used for test selection, so integration tests can be included/excluded with `-m integration` / `-m "not integration"`
3. **`@skip_if_..._integration_tests_disabled`** decorator — skips the test when the required API keys or service endpoints are missing

### Adding New Integration Tests

All three markers must be applied to every new integration test:

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
- **Azure AI integration** — runs when `packages/azure-ai/` or core changes

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
- Use print statements for debugging, then remove them when done
- Resolve all errors and warnings before committing
