# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------
from ._version import VERSION
from .abstract_agent import Agent, AgentThread, AgentRunOptions, MessagesRetrievableThread, MemoryAgentThread, AgentThreadManager
from .chat_completion_agent import ChatClientAgent, ChatClient, ChatClientAgentOptions, ChatClientAgentRunOptions, ChatClientAgentThread
from .simple_agent import SimpleAgent

__version__ = VERSION

__all__ = [
    "Agent",
    "AgentThread",
    "AgentRunOptions",
    "MessagesRetrievableThread",
    "MemoryAgentThread",
    "AgentThreadManager",
    "ChatClientAgent",
    "ChatClient",
    "ChatClientAgentOptions",
    "ChatClientAgentRunOptions",
    "ChatClientAgentThread",
    "SimpleAgent",
    "__version__"
]
