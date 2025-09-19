# Cookiecutter Template for Agent Framework Lab Packages

This is a cookiecutter template for creating new lab packages in the Microsoft Agent Framework.

## Usage

```bash
cd /path/to/agent-framework/python/packages/lab
cookiecutter ./cookiecutter-agent-framework-lab
```

You will be prompted for the following information:

- **package_name**: The name of your lab package (e.g., "lightning", "vision")
- **package_display_name**: Human-readable name (e.g., "Lighting Tools", "Computer Vision")
- **package_description**: Brief description of the package (auto-generated from display name)
- **version**: Starting version (default: 0.1.0b1)
- **author_name**: Author name (default: Microsoft)
- **author_email**: Author email (default: SK-Support@microsoft.com)
- **include_cli_script**: Whether to include a CLI script (y/n)
- **cli_script_name**: Name of CLI script if included

## What Gets Generated

The template creates a complete lab package structure:

```
{package_name}/
├── agent_framework/
│   └── lab/
│       └── {package_name}/
│           └── __init__.py
├── agent_framework_lab_{package_name}/
│   ├── __init__.py
│   └── py.typed
├── tests/
│   ├── __init__.py
│   └── test_{package_name}.py
├── pyproject.toml
├── README.md
└── LICENSE
```

## After Generation

1. Implement your functionality in `agent_framework_lab_{package_name}/`
2. Update the `__all__` exports in `__init__.py`
3. Add your dependencies to `pyproject.toml`
4. Write comprehensive tests
5. Update the README with usage examples

## Integration

Don't forget to add your new package to the workspace:

1. Add to `python/pyproject.toml` dependencies
2. Add to `[tool.uv.sources]` section
3. Test installation with `uv run python -c "from agent_framework.lab.{name} import *"`