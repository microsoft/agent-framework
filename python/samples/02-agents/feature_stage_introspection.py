# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

import agent_framework

"""Feature stage introspection.

This sample demonstrates how to inspect feature lifecycle metadata on Agent
Framework APIs.

The recommended minimal setup for consumers is:
1. Read `__feature_stage__` with `getattr(...)` to see whether an API is staged
2. Read `__feature_id__` with `getattr(...)` only when that metadata is present
3. Treat missing metadata as "no explicit feature-stage annotation"
4. Do not rely on `ExperimentalFeature` or `ReleaseCandidateFeature` membership
    over time, since staged features may move or be removed as they advance

This sample loops through the symbols exported from the root `agent_framework`
module and reports the ones that currently carry feature-stage metadata.
"""


def describe_api(name: str, api: Any) -> None:
    """Print optional feature-stage metadata for one API."""
    feature_stage = getattr(api, "__feature_stage__", "released")
    feature_id = getattr(api, "__feature_id__", None)

    print(f"{name}:")
    print(f"  feature_stage = {feature_stage!r}")
    print(f"  feature_id = {feature_id!r}")


def iter_staged_root_exports() -> list[tuple[str, Any]]:
    """Return root exports that currently carry feature-stage metadata."""
    staged_root_symbols: list[tuple[str, Any]] = []
    for symbol_name in sorted(agent_framework.__all__):
        symbol = getattr(agent_framework, symbol_name)
        feature_stage = getattr(symbol, "__feature_stage__", None)
        feature_id = getattr(symbol, "__feature_id__", None)
        if feature_stage is None and feature_id is None:
            continue
        staged_root_symbols.append((symbol_name, symbol))
    return staged_root_symbols


async def main() -> None:
    """Run the feature-stage introspection sample."""
    print("Feature stage introspection")
    print("-" * 60)

    # 1. Loop through everything exported from the root module.
    staged_root_symbols = iter_staged_root_exports()

    # 2. Show the root exports that currently carry feature-stage metadata.
    if not staged_root_symbols:
        print("No root exports currently carry feature-stage metadata.")
        return

    print("Root exports with feature-stage metadata:")
    for name, api in staged_root_symbols:
        describe_api(name, api)
        print()

    print("Root exports without metadata currently have no explicit feature-stage metadata.")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
Feature stage introspection
------------------------------------------------------------
Root exports with feature-stage metadata:

<export name>:
  feature_stage = 'experimental'
  feature_id = '<feature id>'

Root exports without metadata currently have no explicit feature-stage metadata.
"""
