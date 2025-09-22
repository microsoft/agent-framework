# Agent Framework Lab

This directory contains experimental packages for Microsoft Agent Framework that are distributed as separate installable packages under the `agent_framework.lab` namespace.
Lab packages are not part of the core framework and may experience breaking changes or be deprecated in the future.

## What are Lab Packages?

Lab packages are extensions to the core Agent Framework that falls into
one of the following categories:

1. Incubation of new features that may get incorprated by the core framework.
2. Research prototypes built on the core framework.
3. Benchmarks and experimentation tools.

## Lab Packages

- [**gaia**](./gaia/): GAIA benchmark implementation (`agent-framework-lab-gaia`)
- [**lightning**](./lightning/): Reinforcement learning for agents (`agent-framework-lab-lightning`)

## How do I contribute?

This repo only contains lab packages maintained by Microsoft.
If you want to contribute, please take the following steps:

1. Follow the [Create a New Lab Package](#create-new-lab-package) guide
   below to create your own lab package.
2. Create a new repo on GitHub and check in your package there.
3. Tag your repo with `agent-framework-lab` for bettter discovery.
4. Submit a PR to this repo (github.com/microsoft/agent-framework)
   to add a link to your repo in the [list](#lab-packages) above.
   **The PR title must contain "[New Lab Package]"**.
5. We will review your repo and decide whether to approve it.

Follow the [guidelines](#guidelines) when you create your package, our decision
to accept your PR will be based on your idea as well as the quality of your
code.

We may decide to maintain your package in this repo. In that case, we will
contact you directly.

## Package Structure

Each lab package follows this structure:

```
packages/lab/{lab_name}/
├── agent_framework/
│   └── lab/
│       └── {lab_name}/
│           └── __init__.py          # Imports from agent_framework_lab_{lab_name}
├── agent_framework_lab_{lab_name}/ # Actual implementation package
│   ├── __init__.py                  # Main exports and __version__
│   ├── {module_files}.py           # Implementation modules
│   └── py.typed                     # Type hints marker
├── tests/
│   ├── __init__.py
│   └── test_{lab_name}.py          # Package tests
├── pyproject.toml                   # Package configuration
├── README.md                        # Package-specific documentation
└── LICENSE                          # MIT License
```

## Creating a New Lab Package

### Create The Package

First ensure `cookiecutter` is installed.

```bash
pip install cookiecutter
```

Then go to the directory where you want to create the package:

```bash
cookiecutter /path/to/agent-framework/python/packages/lab/cookiecutter-agent-framework-lab
```

You will be prompted for:

- **package_name**: The name of your lab package (e.g., "lightning", "vision")
- **package_display_name**: Human-readable name (e.g., "Lighting Tools", "Computer Vision")
- **package_description**: Brief description (auto-generated from display name)
- **include_cli_script**: Whether to include a CLI script (y/n)

### After Package Creation

1. **Implement your functionality** in `agent_framework_lab_your_package_name/`
2. **Update exports** in `__init__.py` `__all__` list
3. **Add dependencies** to `pyproject.toml`
4. **Write tests** in the `tests/` directory
5. **Update README** with usage examples and API documentation

### Add to Workspace (only for packages maintained in this repo)

After creating your package, add it to the workspace configuration:

```
# Edit python/pyproject.toml
# Add to dependencies section:
dependencies = [
    # ... existing packages ...
    "agent-framework-lab-your-package-name",
]

# Add to [tool.uv.sources] section:
agent-framework-lab-your-package-name = { workspace = true }
```

### Usage

Once created, users can install your lab package

1. directly from your repo:

```bash
pip install git+https://github.com/your-username/your-lab-package-repo.git
```

2. or from PyPI if you have uploaded your lab package there:

```bash
pip install "agent-framework-lab-your-package-name"
```

Then, they can use your lab package:

```python
from agent_framework.lab.your_package_name import YourClass, your_function

# Use the functionality
instance = YourClass()
result = your_function()
```

## Guidelines

1. **Naming**: Use lowercase with hyphens for package names (`agent-framework-lab-your-package-name`)
2. **Namespace**: Always use `agent_framework.lab.your_package_name` for imports
3. **Versioning**: Start with `0.1.0b1` for beta releases
4. **Dependencies**: Minimize external dependencies, always include `agent-framework`
5. **Documentation**: Include comprehensive README with usage examples
6. **Tests**: Write comprehensive tests with good coverage
7. **Type hints**: Always include type hints and `py.typed` file
