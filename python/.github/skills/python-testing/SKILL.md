---
name: python-testing
description: >
  Guidelines for writing and running tests in the Agent Framework Python
  codebase. Use this when creating, modifying, or running tests.
---

# Python Testing

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
```

## Test Configuration

- **Async mode**: `asyncio_mode = "auto"` is enabled — do NOT use `@pytest.mark.asyncio`
- **Timeout**: Default 60 seconds per test
- **Import mode**: `importlib` for cross-package isolation

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
- Factory functions with parameters should be regular functions, not fixtures
- Import factory functions explicitly: `from conftest import create_test_request`
- Use descriptive names: `mapper`, `test_request`, `mock_client`

## File Naming

- Files starting with `test_` are test files — do not use this prefix for helpers
- Use `conftest.py`, `helpers.py`, or `fixtures.py` for shared utilities

## Integration Tests

Tests marked with `@skip_if_..._integration_tests_disabled` require:
- `RUN_INTEGRATION_TESTS=true` environment variable
- Appropriate API keys in environment or `.env` file

## Best Practices

- Run only related tests, not the entire suite
- Review existing tests to understand coding style before creating new ones
- Use print statements for debugging, then remove them when done
- Resolve all errors and warnings before committing
