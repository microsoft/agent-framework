# Try the Python agent-framework from the repository

This page shows how an external Python application (not working inside this repo) can install and use the Python packages provided by this repository directly from the `main` branch on GitHub, in lieu of waiting for a PyPI release.

Globally, these are the steps:
- Create a requirements.txt and constraints.txt (or a pyproject.toml) or a uv pyproject.toml
- Create and activate a virtual environment
- Install the main package with extras from the repo using pip or uv
- Verify the installation

## Quick summary
- Minimum Python: >= 3.10 (project requires-python = ">=3.10").
- GitHub repository: https://github.com/microsoft/agent-framework.
- Package subdirectories used by pip:
	- Main package: `python/packages/main`
	- Azure: `python/packages/azure`
	- Foundry: `python/packages/foundry`
	- Workflow: `python/packages/workflow`

Why use the repo URL?
- Installing from the GitHub repo lets you try the current `main` branch without waiting for a PyPI release, once we start releasing our packages on PyPI we will remove this guide.

Important note about extras and sub-packages
- The `agent-framework` package defines optional extras (for example `azure`, `foundry`, `workflow`) which declare dependency names like `agent-framework-azure`.
- Installing `agent-framework[azure]` from the repo will instruct pip to request the distribution `agent-framework-azure`. This package is also not published on PyPI (or an index pip knows about), pip may fail to resolve the extra automatically, so you need to explicitly tell pip where to find that package.

To do this with pip, you can use a `--constraint` file that pins the subpackages to the repo URL while installing the main package with extras, see the quick start example below.

# Quick start — install the main package from GitHub in a new virtual environment

### Approach 1) using requirements.txt + constraints.txt

Create and activate a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

For example, when you want to use Agent Framework with Azure OpenAI clients, use a requirements.txt like this:

```
agent-framework[azure] @ git+https://github.com/microsoft/agent-framework.git@main#subdirectory=python/packages/main
```

with constraints for the extras, in constraints.txt:

```
agent-framework-azure @ git+https://github.com/microsoft/agent-framework.git@main#subdirectory=python/packages/azure
agent-framework-foundry @ git+https://github.com/microsoft/agent-framework.git@main#subdirectory=python/packages/foundry
agent-framework-workflow @ git+https://github.com/microsoft/agent-framework.git@main#subdirectory=python/packages/workflow
```

Then install with:

```bash
pip install -r requirements.txt --constraint constraints.txt
```

### Approach 2) or using [`uv`](https://docs.astral.sh/uv/getting-started/installation/) with `pyproject.toml`

First create a pyproject.toml with the dependency and source mappings, for example:
```toml
[project]
name = "my-app"
requires-python = ">=3.10"
dependencies = [
    "agent-framework[azure]", # or [azure,workflow]
]
[tool.uv]
prerelease = "if-necessary-or-explicit"
[tool.uv.sources]
"agent-framework" = { git = "https://github.com/microsoft/agent-framework.git", ref = "main", subdirectory = "python/packages/main" }
"agent-framework-azure" = { git = "https://github.com/microsoft/agent-framework.git", ref = "main", subdirectory = "python/packages/azure" }
"agent-framework-foundry" = { git = "https://github.com/microsoft/agent-framework.git", ref = "main", subdirectory = "python/packages/foundry" }
"agent-framework-workflow" = { git = "https://github.com/microsoft/agent-framework.git", ref = "main", subdirectory = "python/packages/workflow" }
```
Then create a virtual environment:
```bash
uv venv
```

Then install with:

```bash
uv sync
```

## Quick verification

To verify the installation, you can run a Python shell (from your virtual environment) and try to import the main package and any extras you installed, for example (and you can uncomment the extras you installed):

```python
from agent_framework import __version__ as af_version
# from agent_framework.azure import __version__ as af_azure_version
# from agent_framework.foundry import __version__ as af_foundry_version
# from agent_framework.workflow import __version__ as af_workflow_version
print(f"Main package: {af_version}")
# print(f"Azure extra: {af_azure_version}")
# print(f"Foundry extra: {af_foundry_version}")
# print(f"Workflow extra: {af_workflow_version}")
```
This should print the version of the main package, for example:
```
Main package: 0.1.0b1
```

Next, you can review the get started guides in [user-guide](../user-guide/README.md) to try out the functionality of the agent framework.
