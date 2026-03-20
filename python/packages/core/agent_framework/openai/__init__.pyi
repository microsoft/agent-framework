# Copyright (c) Microsoft. All rights reserved.

# This is a dynamic namespace — all symbols are lazily loaded from agent-framework-openai.
from typing import Any

def __getattr__(name: str) -> Any: ...  # pyright: ignore[reportIncompleteStub]
def __dir__() -> list[str]: ...
