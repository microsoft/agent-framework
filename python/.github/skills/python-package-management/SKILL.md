---
name: python-package-management
description: >
  Guide for managing packages in the Agent Framework Python monorepo, including
  creating new connector packages, versioning, and the lazy-loading pattern.
  Use this when adding, modifying, or releasing packages.
---

# Python Package Management

## Monorepo Structure

```
python/
├── pyproject.toml              # Root package (agent-framework)
├── packages/
│   ├── core/                   # agent-framework-core (main package)
│   ├── azure-ai/               # agent-framework-azure-ai
│   ├── anthropic/              # agent-framework-anthropic
│   └── ...                     # Other connector packages
```

- `agent-framework-core` contains core abstractions and OpenAI/Azure OpenAI built-in
- Provider packages extend core with specific integrations
- Root `agent-framework` depends on `agent-framework-core[all]`

## Dependency Management

Uses [uv](https://github.com/astral-sh/uv) for dependency management and
[poethepoet](https://github.com/nat-n/poethepoet) for task automation.

```bash
# Full setup (venv + install + prek hooks)
uv run poe setup

# Install/update all dependencies
uv run poe install

# Create venv with specific Python version
uv run poe venv --python 3.12
```

## Lazy Loading Pattern

Provider folders in core use `__getattr__` to lazy load from connector packages:

```python
# In agent_framework/azure/__init__.py
_IMPORTS: dict[str, tuple[str, str]] = {
    "AzureAIAgentClient": ("agent_framework_azure_ai", "agent-framework-azure-ai"),
}

def __getattr__(name: str) -> Any:
    if name in _IMPORTS:
        import_path, package_name = _IMPORTS[name]
        try:
            return getattr(importlib.import_module(import_path), name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"The package {package_name} is required to use `{name}`. "
                f"Install it with: pip install {package_name}"
            ) from exc
```

## Adding a New Connector Package

**Important:** Do not create a new package unless approved by the core team.

### Initial Release (Preview)

1. Create directory under `packages/` (e.g., `packages/my-connector/`)
2. Add the package to `tool.uv.sources` in root `pyproject.toml`
3. Include samples inside the package (e.g., `packages/my-connector/samples/`)
4. Do **NOT** add to `[all]` extra in `packages/core/pyproject.toml`
5. Do **NOT** create lazy loading in core yet

### Promotion to Stable

1. Move samples to root `samples/` folder
2. Add to `[all]` extra in `packages/core/pyproject.toml`
3. Create provider folder in `agent_framework/` with lazy loading `__init__.py`

## Versioning

- All non-core packages declare a lower bound on `agent-framework-core`
- When core version bumps with breaking changes, update the lower bound in all packages
- Non-core packages version independently; only raise core bound when using new core APIs

## Installation Options

```bash
pip install agent-framework-core          # Core only
pip install agent-framework-core[all]     # Core + all connectors
pip install agent-framework               # Same as core[all]
pip install agent-framework-azure-ai      # Specific connector (pulls in core)
```

## Maintaining Documentation

When changing a package, check if its `AGENTS.md` needs updates:
- Adding/removing/renaming public classes or functions
- Changing the package's purpose or architecture
- Modifying import paths or usage patterns
