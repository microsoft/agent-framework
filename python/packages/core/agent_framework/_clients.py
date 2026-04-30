

# Import at the end of the module so the symbol is explicitly available
# for typing and introspection while still minimizing circular import risk.
from ._fake_chat_client import FakeChatClient  # noqa: E402
