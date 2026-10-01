# Copyright (c) Microsoft. All rights reserved.

import subprocess
import sys
import textwrap


def test_package_import_is_lazy() -> None:
    code = textwrap.dedent(
        """
        import sys

        import agent_framework_foundry_hosting

        assert "agent_framework_foundry_hosting._invocations" not in sys.modules
        assert "agent_framework_foundry_hosting._responses" not in sys.modules
        assert "agent_framework_foundry_hosting._scope" not in sys.modules
        assert "agent_framework_foundry_hosting._state_store" not in sys.modules
        assert "agent_framework_foundry_hosting._toolbox" not in sys.modules
        assert "agent_framework_foundry_hosting._workflow_source" not in sys.modules
        assert "agent_framework_foundry_hosting._workflow_state" not in sys.modules
        """
    )
    subprocess.run([sys.executable, "-I", "-c", code], check=True)


def test_native_workflow_exports_match_runtime_and_typing_namespace() -> None:
    import agent_framework.foundry as foundry

    import agent_framework_foundry_hosting as hosting

    for name in ("WorkflowTurn", "WorkflowSource"):
        assert name in hosting.__all__
        assert getattr(foundry, name) is getattr(hosting, name)
