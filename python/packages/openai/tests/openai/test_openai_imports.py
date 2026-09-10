# Copyright (c) Microsoft. All rights reserved.

import subprocess
import sys
import textwrap


def test_package_import_is_lazy() -> None:
    code = textwrap.dedent(
        """
        import sys

        import agent_framework_openai

        assert "agent_framework_openai._chat_client" not in sys.modules
        assert "agent_framework_openai._chat_completion_client" not in sys.modules
        assert not any(name == "openai" or name.startswith("openai.") for name in sys.modules)
        """
    )
    subprocess.run([sys.executable, "-I", "-c", code], check=True)
