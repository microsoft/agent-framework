# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from xml.etree import ElementTree

import pytest


@pytest.mark.parametrize("original_root", [None, "existing-state-root"])
@pytest.mark.parametrize("failures", [1, 3], ids=["passes-on-retry", "exhausts-retries"])
def test_state_root_is_isolated_and_cleaned_per_attempt(
    tmp_path: Path, original_root: str | None, failures: int
) -> None:
    fixture_source = (Path(__file__).parents[1] / "conftest.py").read_text(encoding="utf-8")
    (tmp_path / "conftest.py").write_text(
        fixture_source
        + textwrap.dedent(
            f"""

            import os

            @pytest.hookimpl(tryfirst=True)
            def pytest_runtest_setup():
                assert os.environ.get("AGENTSERVER_STATE_ROOT") == {original_root!r}

            def pytest_sessionfinish():
                assert os.environ.get("AGENTSERVER_STATE_ROOT") == {original_root!r}
            """
        ),
        encoding="utf-8",
    )
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "test_retry.py").write_text(
        textwrap.dedent(
            f"""
            import os
            from pathlib import Path

            import pytest

            roots = []

            @pytest.mark.flaky
            def test_retry():
                root = Path(os.environ["AGENTSERVER_STATE_ROOT"])
                with Path("roots.txt").open("a", encoding="utf-8") as log:
                    log.write(str(root) + "\\n")
                assert root.name == "agentserver-state"
                assert root.parent.is_dir()
                assert not root.exists()
                assert root not in roots
                assert all(not previous.parent.exists() for previous in roots)
                roots.append(root)
                root.mkdir()
                (root / "state.txt").write_text("attempt state", encoding="utf-8")
                assert len(roots) > {failures}, "Synthetic attempt failure"
            """
        ),
        encoding="utf-8",
    )
    # Isolate only the child harness, which needs pytest-retry but no application plugins.
    env: dict[str, str] = {
        **os.environ,
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTEST_ADDOPTS": "",
        "PYTEST_PLUGINS": "",
    }
    if original_root is None:
        env.pop("AGENTSERVER_STATE_ROOT", None)
    else:
        env["AGENTSERVER_STATE_ROOT"] = original_root
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "pytest",
            "-p",
            "pytest_retry.retry_plugin",
            "--import-mode=importlib",
            "--retries=2",
            "--retry-delay=0",
            "--junitxml=results.xml",
            "-q",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == (0 if failures == 1 else 1), output
    suite = ElementTree.parse(tmp_path / "results.xml").getroot().find("testsuite")
    assert suite is not None, output
    assert suite.attrib["tests"] == "1", output
    assert suite.attrib["errors"] == "0", output
    assert suite.attrib["failures"] == ("0" if failures == 1 else "1"), output
    if failures == 3:
        assert "Synthetic attempt failure" in output
    roots = (tmp_path / "roots.txt").read_text(encoding="utf-8").splitlines()
    assert len(roots) == len(set(roots)) == min(failures + 1, 3)
    assert all(not Path(root).parent.exists() for root in roots)
