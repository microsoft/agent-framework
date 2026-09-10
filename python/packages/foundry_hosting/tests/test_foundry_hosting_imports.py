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
        assert "agent_framework_foundry_hosting._state_store" not in sys.modules
        assert "agent_framework_foundry_hosting._toolbox" not in sys.modules
        """
    )
    subprocess.run([sys.executable, "-I", "-c", code], check=True)
