# Copyright (c) Microsoft. All rights reserved.

"""Parse lazy namespace exports and their type stubs without importing connectors."""

import ast
from pathlib import Path

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
