# Copyright (c) Microsoft. All rights reserved.

"""Keep the lazy ``agent_framework.<namespace>`` modules and their type stubs in sync.

Each namespace re-exports connector classes lazily through ``_IMPORTS`` and declares
the same names in ``__init__.pyi`` for type checkers. A name missing from the stub
imports fine at runtime but is rejected by type checkers, so compare them statically.
"""

import ast
from pathlib import Path

import pytest

_PACKAGE_ROOT = Path(__file__).parents[2] / "agent_framework"


def _lazy_namespaces() -> list[Path]:
    namespaces: list[Path] = []
    for init in sorted(_PACKAGE_ROOT.glob("*/__init__.py")):
        if _lazy_imports(init) is not None:
            namespaces.append(init.parent)
    return namespaces


def _lazy_imports(init: Path) -> dict[str, str | None] | None:
    """Return the lazily exported names mapped to their source module, if declared."""
    module = ast.parse(init.read_text(encoding="utf-8"))
    import_path: str | None = None
    for node in module.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, assigned = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, assigned = node.target, node.value
        else:
            continue
        if not isinstance(target, ast.Name):
            continue
        if target.id == "IMPORT_PATH":
            import_path = ast.literal_eval(assigned)
        elif target.id == "_IMPORTS":
            value = ast.literal_eval(assigned)
            if isinstance(value, dict):
                return {name: source[0] for name, source in value.items()}
            return dict.fromkeys(value, import_path)
    return None


def _stub_exports(stub: Path) -> tuple[dict[str, str | None], set[str]]:
    module = ast.parse(stub.read_text(encoding="utf-8"))
    imported: dict[str, str | None] = {}
    exported: set[str] = set()
    for node in module.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported[alias.asname or alias.name] = node.module
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            exported = set(ast.literal_eval(node.value))
    return imported, exported


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
