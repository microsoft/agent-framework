# Agent Framework Lab

This is the experimental package for Microsoft Agent Framework, `agent-framework-lab`, which contains
various lab modules built on top of the core framework.
Lab modules are not part of the core framework and may experience breaking changes or be deprecated in the future.

## What are Lab Modules?

Lab modules are extensions to the core Agent Framework that fall into
one of the following categories:

1. Incubation of new features that may get incorporated by the core framework.
2. Research prototypes built on the core framework.
3. Benchmarks and experimentation tools.

## Lab Modules

- [**gaia**](./gaia/): Evaluate your agents using the GAIA benchmark for general assistant tasks
- [**tau2**](./tau2/): Evaluate your agents using the TAU2 benchmark for customer support tasks
- [**lightning**](./lightning/): RL training for agents using Agent Lightning

## Repository Structure

```
agent-framework-lab/
├── pyproject.toml          # Single package configuration for agent-framework-lab
├── README.md               # This file
├── LICENSE                 # License file
├── namespace/              # Centralized namespace package files
│   └── agent_framework/
│       └── lab/
│           ├── gaia/       # Re-exports from agent_framework_lab_gaia
│           ├── lightning/  # Re-exports from agent_framework_lab_lightning
│           └── tau2/       # Re-exports from agent_framework_lab_tau2
├── gaia/                   # GAIA module implementation
│   └── agent_framework_lab_gaia/
├── lightning/              # Lightning module implementation
│   └── agent_framework_lab_lightning/
└── tau2/                   # TAU2 module implementation
    └── agent_framework_lab_tau2/
```

This structure maintains a single PyPI package `agent-framework-lab` while supporting modular imports through the namespace package mechanism.

## Installation

To install each lab module, use the extras syntax with `pip`:

```bash
pip install "agent-framework-lab[gaia]"
pip install "agent-framework-lab[tau2]"
pip install "agent-framework-lab[lightning]"
```

## Usage

Import and use lab modules from the `agent_framework.lab` namespace.
For example, to use the GAIA module:

```python
# Using GAIA module
from agent_framework.lab.gaia import GAIA
```

## Should I consume Lab Modules?

If you are looking for stable and production-ready features, you should not use lab modules. Stick to the core framework.

If you are looking for experimentation, research, or want to
benchmark different approaches -- most importantly, if you don't mind breaking changes and potential deprecations --
then lab modules are for you.

## Contributing to Lab Modules

### Microsoft-maintained modules

For Microsoft-maintained modules in this repository, please follow standard contribution guidelines and submit pull requests directly to this repository.

### Community modules

If you want to contribute a community-maintained lab module:

1. Create a new repository on GitHub for your module
2. Tag your repository with `agent-framework-lab` for discoverability
3. Submit a PR to add a link to your repository in the [Lab Modules](#lab-modules) section above
4. Use the PR title format: `[New Lab Module] Your Module Name`

We will review your submission based on the guidelines below.

### Guidelines

1. **Purpose**: Community modules should fit into one of the three categories of lab modules (incubation, research, benchmarks)
2. **Namespace**: Community modules should avoid the `agent_framework.lab` namespace (reserved for modules maintained in this repository)
3. **Dependencies**: Minimize external dependencies, always include `agent-framework` as a base dependency
4. **Documentation**: Include comprehensive README with installation instructions and usage examples
5. **Tests**: Write comprehensive tests with good coverage
6. **Type hints**: Always include type hints and a `py.typed` file
7. **Versioning**: Use semantic versioning, start with `0.1.0` for initial releases
