# Copyright (c) Microsoft. All rights reserved.

"""Keep the lazy ``agent_framework.<namespace>`` modules and their type stubs in sync.

Each namespace re-exports connector classes lazily through ``_IMPORTS`` and declares
the same names in ``__init__.pyi`` for type checkers. A name missing from the stub
imports fine at runtime but is rejected by type checkers, so compare them statically.
"""

from pathlib import Path

import pytest

from .namespace_stubs_helpers import _lazy_imports, _lazy_namespaces, _stub_exports


@pytest.mark.parametrize("namespace", _lazy_namespaces(), ids=lambda path: path.name)
def test_namespace_stub_declares_every_lazy_export(namespace: Path) -> None:
    lazy_imports = _lazy_imports(namespace / "__init__.py")
    assert lazy_imports is not None
    stub = namespace / "__init__.pyi"
    assert stub.exists(), f"agent_framework.{namespace.name} has lazy exports but no __init__.pyi"

    stub_imports, stub_all = _stub_exports(stub)

    assert set(stub_imports) == set(lazy_imports)
    assert stub_all == set(lazy_imports)
    for name, source in lazy_imports.items():
        stub_source = stub_imports[name]
        assert source is not None
        assert stub_source is not None
        # The stub may import from a submodule of the same distribution package.
        assert stub_source.split(".")[0] == source.split(".")[0], name
