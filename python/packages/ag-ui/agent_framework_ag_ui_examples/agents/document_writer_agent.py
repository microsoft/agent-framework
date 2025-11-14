# Copyright (c) Microsoft. All rights reserved.

"""Example agent demonstrating predictive state updates with document writing."""

from agent_framework import ChatAgent, ai_function
from agent_framework._clients import ChatClientProtocol

from agent_framework_ag_ui import AgentFrameworkAgent, DocumentWriterConfirmationStrategy


@ai_function
def write_document_local(document: str) -> str:
    """Write a document. Use markdown formatting to format the document.

    It's good to format the document extensively so it's easy to read.
    You can use all kinds of markdown.
    However, do not use italic or strike-through formatting, it's reserved for another purpose.
    You MUST write the full document, even when changing only a few words.
    When making edits to the document, try to make them minimal - do not change every word.
    Keep stories SHORT!

    Args:
        document: The complete document content in markdown format

    Returns:
        Confirmation that the document was written
    """
    return "Document written."


_DOCUMENT_WRITER_INSTRUCTIONS = (
    "You are a helpful assistant for writing documents. "
    "To write the document, you MUST use the write_document_local tool. "
    "You MUST write the full document, even when changing only a few words. "
    "When you wrote the document, DO NOT repeat it as a message. "
    "Just briefly summarize the changes you made. 2 sentences max. "
    "\n\n"
    "The current state of the document will be provided to you. "
    "When editing, make minimal changes - do not change every word unless requested."
)


def document_writer_agent(chat_client: ChatClientProtocol) -> AgentFrameworkAgent:
    """Create a document writer agent with predictive state updates.

    Args:
        chat_client: The chat client to use for the agent

    Returns:
        A configured AgentFrameworkAgent instance with document writing capabilities
    """
    agent = ChatAgent(
        name="document_writer",
        instructions=_DOCUMENT_WRITER_INSTRUCTIONS,
        chat_client=chat_client,
        tools=[write_document_local],
    )

    return AgentFrameworkAgent(
        agent=agent,
        name="DocumentWriter",
        description="Writes and edits documents with predictive state updates",
        state_schema={
            "document": {"type": "string", "description": "The current document content"},
        },
        predict_state_config={
            "document": {"tool": "write_document_local", "tool_argument": "document"},
        },
        confirmation_strategy=DocumentWriterConfirmationStrategy(),
    )
