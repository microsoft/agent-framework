# Lab Package (agent-framework-lab)

Experimental packages for cutting-edge features including benchmarking, reinforcement learning, and research initiatives.

## Structure

This package contains experimental sub-packages:

- `gaia/` - GAIA benchmark integration
- `lightning/` - Lightning-based training utilities
- `tau2/` - Tau-bench evaluation framework
- `namespace/` - Experimental namespace utilities

## Note

Lab packages are experimental and may change frequently. They are not included in the standard `agent-framework[all]` installation.

Lab is a standalone uv project, excluded from the root `python` workspace so its experimental dependencies do not
constrain released provider packages. It resolves released Core and provider distributions by default. Run dependency
and validation commands from `python/packages/lab`.

## Cross-Package Changes

Lab code must use APIs available in published Agent Framework distributions. If a Lab change needs an unreleased
Core, OpenAI adapter, or other provider change, merge and release that dependency first. After the release is
available, raise the corresponding Lab dependency floor when needed, refresh this directory's lockfile, and then
implement the Lab change.

For example, a Lab feature that depends on a new `agent-framework-openai` API must wait for an
`agent-framework-openai` release containing that API. Do not add a root-workspace or local-path source override to
bypass this sequence; that would restore the dependency coupling this project boundary exists to prevent.

## Installation

```bash
pip install agent-framework-lab
```

## Development

```bash
uv sync --all-extras --all-groups
uv run poe test
uv run poe pyright
```

Lab maintains its own `uv.lock`. Do not update the root `python/uv.lock` for Lab-only dependency changes.
