# Copyright (c) Microsoft. All rights reserved.

import subprocess
import sys
import textwrap


def _run_isolated(code: str) -> None:
    subprocess.run([sys.executable, "-I", "-c", textwrap.dedent(code)], check=True)


def test_package_import_is_lazy() -> None:
    _run_isolated(
        """
        import sys

        import agent_framework_foundry

        assert "agent_framework_foundry._chat_client" not in sys.modules
        assert "agent_framework_foundry._memory_provider" not in sys.modules
        assert not any(name == "openai" or name.startswith("openai.") for name in sys.modules)
        """
    )


def test_lightweight_exports_do_not_import_openai() -> None:
    _run_isolated(
        """
        import sys

        from agent_framework_foundry import (
            FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY,
            FoundryEmbeddingClient,
            FoundryEvals,
            FoundryMemoryProvider,
            to_prompt_agent,
        )

        assert FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY == "foundry_hosted_agent_session_id"
        assert FoundryEmbeddingClient.__name__ == "FoundryEmbeddingClient"
        assert FoundryEvals.__name__ == "FoundryEvals"
        assert FoundryMemoryProvider.__name__ == "FoundryMemoryProvider"
        assert callable(to_prompt_agent)
        assert not any(name == "openai" or name.startswith("openai.") for name in sys.modules)
        """
    )
