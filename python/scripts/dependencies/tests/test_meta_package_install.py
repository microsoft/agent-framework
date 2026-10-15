# Copyright (c) Microsoft. All rights reserved.

import json
import re
import subprocess
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from zipfile import ZipFile

import pytest
import yaml


def _write_wheel(directory: Path, name: str, version: str, dependencies: list[str]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    normalized_name = name.replace("-", "_")
    wheel = directory / f"{normalized_name}-{version}-py3-none-any.whl"
    metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    metadata += "".join(f"Requires-Dist: {dependency}\n" for dependency in dependencies)
    dist_info = f"{normalized_name}-{version}.dist-info"
    with ZipFile(wheel, "w") as archive:
        archive.writestr(f"{dist_info}/METADATA", metadata)
        archive.writestr(
            f"{dist_info}/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr(f"{dist_info}/RECORD", "")
    return wheel


@pytest.mark.parametrize("step_name", ["Resolve the end-user install", "Install and import the meta package"])
def test_meta_install_uses_built_wheels_instead_of_same_version_registry_metadata(
    tmp_path: Path, step_name: str
) -> None:
    workspace = tmp_path / "workspace with spaces"
    wheelhouse = workspace / "wheelhouse"
    _write_wheel(wheelhouse, "agent-framework", "1.0.1", ["agent-framework-core==1.0.1"])
    _write_wheel(wheelhouse, "agent-framework-core", "1.0.1", ["agent-framework-foundry-hosting==1.0.0b1", "mcp>=2,<3"])
    hosting = _write_wheel(wheelhouse, "agent-framework-foundry-hosting", "1.0.0b1", ["mcp>=2,<3"])
    registry = tmp_path / "registry"
    registry_hosting = registry / "simple" / "agent-framework-foundry-hosting"
    published = _write_wheel(registry_hosting, "agent-framework-foundry-hosting", "1.0.0b1", ["mcp<2"])
    (registry_hosting / "index.html").write_text(f'<a href="{published.name}">{published.name}</a>', encoding="utf-8")
    registry_mcp = registry / "simple" / "mcp"
    mcp = _write_wheel(registry_mcp, "mcp", "2.2.0", [])
    (registry_mcp / "index.html").write_text(f'<a href="{mcp.name}">{mcp.name}</a>', encoding="utf-8")

    workflow_path = Path(__file__).resolve().parents[4] / ".github" / "workflows" / "python-tests.yml"
    steps = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))["jobs"]["python-meta-package-install"]["steps"]
    for step in steps:
        if step.get("name") == "Constrain workspace packages to built wheels":
            subprocess.run(
                ["pwsh", "-NoProfile", "-NonInteractive", "-Command", step["run"]],
                cwd=workspace,
                check=True,
                capture_output=True,
                text=True,
            )

    install_script = next(step["run"] for step in steps if step.get("name") == step_name)
    selection_arguments = [
        value
        for flag in ("--find-links", "--constraint")
        for argument in re.findall(rf"{flag}\s+(\S+)", install_script)
        for value in (flag, argument)
    ]
    report = workspace / "report.json"
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(registry)))
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        command = [
            sys.executable,
            "-m",
            "pip",
            "--isolated",
            "install",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "--ignore-installed",
            "--index-url",
            f"http://127.0.0.1:{server.server_port}/simple",
            "--report",
            str(report),
            *selection_arguments,
            "agent-framework==1.0.1",
        ]
        if step_name == "Resolve the end-user install":
            command.append("--dry-run")
        else:
            command.extend(["--target", str(workspace / "installed")])
        result = subprocess.run(command, cwd=workspace, capture_output=True, text=True, timeout=30)
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join()

    assert result.returncode == 0, result.stdout + result.stderr
    installed = json.loads(report.read_text(encoding="utf-8"))["install"]
    selected_hosting = next(item for item in installed if item["metadata"]["name"] == "agent-framework-foundry-hosting")
    assert selected_hosting["download_info"]["url"] == hosting.as_uri()
    selected_mcp = next(item for item in installed if item["metadata"]["name"] == "mcp")
    assert selected_mcp["download_info"]["url"].startswith("http://127.0.0.1:")
