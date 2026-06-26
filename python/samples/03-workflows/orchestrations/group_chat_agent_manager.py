# Copyright (c) Microsoft. All rights reserved.

import asyncio
import dataclasses
import os
from typing import AsyncIterator, Callable, Optional, cast

from agent_framework import (
    Agent,
    AgentResponseUpdate,
    Event,
    Message,
)
from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import GroupChatBuilder
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

MessageInterceptor = Callable[[Message], Optional[Message]]

def compose_middleware(*middlewares: MessageInterceptor) -> MessageInterceptor:
    """Chain multiple interceptors. Execution stops early if any returns None."""
    def chained_interceptor(msg: Message) -> Optional[Message]:
        current = msg
        for mw in middlewares:
            current = mw(current)
            if current is None:
                break
        return current
    return chained_interceptor

# 1. CONTENT FILTERING: Drop or redact messages containing sensitive terms
def create_content_filter(forbidden_terms: list[str], redact_instead: bool = True) -> MessageInterceptor:
    def interceptor(msg: Optional[Message]) -> Optional[Message]:
        if msg is None:
            return None
        if msg.role != "assistant" or not msg.text:
            return msg
        
        text_lower = msg.text.lower()
        if any(term.lower() in text_lower for term in forbidden_terms):
            if redact_instead:
                safe_text = "[REDACTED BY MIDDLEWARE]"
                if hasattr (msg,"replace"):
                    try :
                        return msg.replace(text = safe_text)
                    except TypeError:
                        pass
                return Message (role = msg.role, author_name = msg.author_name, text = safe_text)
            print(f"\n[MIDDLEWARE]  Content Filter: Dropped message from '{msg.author_name}'")
            return None
        return msg
    return interceptor

# 2. MESSAGE TRANSFORMATION: Add metadata prefixes for audit/tracing 
def create_message_tagger(prefix: str) -> MessageInterceptor:
    def interceptor(msg: Message) -> Optional[Message]:
        if msg.role == "user" or not msg.text:
            return msg
            
        new_text = f"[{prefix}] {msg.text}"
        try:
            return msg.replace(text=new_text) if hasattr(msg, "replace") else Message(
                role=msg.role, author_name=msg.author_name, text=new_text
            )
        except Exception as e:
            print(f"\n[MIDDLEWARE]  Transformation failed: {e}")
            return msg
    return interceptor

# 3. ACCESS CONTROL: Restrict messages from specific agents
def create_sender_blocklist(blocked_agents: set[str]) -> MessageInterceptor:
    def interceptor(msg: Message) -> Optional[Message]:
        if msg.author_name in blocked_agents:
            print(f"\n[MIDDLEWARE]  Access Control: Blocked message from '{msg.author_name}'")
            return None
        return msg
    return interceptor

# WORKFLOW WRAPPER
async def run_with_message_middleware(
    workflow,
    task: str,
    middleware: MessageInterceptor,
    *,
    stream: bool = True,
) -> AsyncIterator[Event]:

    async for event in workflow.run(task, stream=stream):

        #  INTERMEDIATE EVENTS
        if event.type == "intermediate" and isinstance(event.data, AgentResponseUpdate):
            original_text = event.data.text

            if original_text:
                temp_msg = Message(
                    role=event.data.role or "assistant",
                    author_name=event.data.author_name,
                    text=original_text
                )

                intercepted = middleware(temp_msg)

                if intercepted is None:
                    continue  

                if intercepted.text != original_text:
                    new_data = dataclasses.replace(
                        event.data,
                        text=intercepted.text
                    )
                    event = dataclasses.replace(event, data=new_data)

        #  OUTPUT EVENTS
        elif event.type == "output" and isinstance(event.data, list):
            filtered_messages = []

            for msg in event.data:
                if isinstance(msg, Message):
                    processed = middleware(msg)
                    if processed is not None:
                        filtered_messages.append(processed)
            event = dataclasses.replace(event, data=filtered_messages)
        yield event
"""
Sample: Group Chat with Agent-Based Manager + Message Middleware

What it does:
- Demonstrates middleware integration for message interception between agents
- Manager coordinates Researcher and Writer collaboratively
- Middleware filters, tags, and controls message flow in real-time

Middleware Use Cases & Patterns:
1. Content Filtering: Compliance, PII/secret prevention, toxicity control
2. Tagging/Transformation: Audit tagging, format enforcement, prompt sanitization
3. Access Control: Multi-tenant routing, cost gates, agent permissioning
4. Ordering in this sample: Content Filter → Tagger → Access Control
5. Failure Mode: Dropping messages (`None`) removes context → prefer redaction tokens
6. Integration Note: This sample uses a wrapper pattern. Native hooks (e.g., 
.with_middleware()) can be added to GroupChatBuilder in future framework versions.

Prerequisites:
- FOUNDRY_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- FOUNDRY_MODEL must be set to your Azure OpenAI model deployment name.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing.
"""

ORCHESTRATOR_AGENT_INSTRUCTIONS = """
You coordinate a team conversation to solve the user's task.

Guidelines:
- Start with Researcher to gather information
- Then have Writer synthesize the final answer
- Only finish after both have contributed meaningfully
"""

async def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    orchestrator_agent = Agent(
        name="Orchestrator",
        description="Coordinates multi-agent collaboration by selecting speakers",
        instructions=ORCHESTRATOR_AGENT_INSTRUCTIONS,
        client=client,
    )

    researcher = Agent(
        name="Researcher",
        description="Collects relevant background information",
        instructions="Gather concise facts that help a teammate answer the question.",
        client=client,
    )

    writer = Agent(
        name="Writer",
        description="Synthesizes polished answers from gathered information",
        instructions="Compose clear and structured answers using any notes provided.",
        client=client,
    )

    middleware_pipeline = compose_middleware(
        create_content_filter(forbidden_terms=["confidential", "internal-ip", "password"]),
        create_message_tagger(prefix="AUDIT"),
        # Use a clearly non-existent agent name so this sample demonstrates
        # sender blocking without affecting the current participants.
        create_sender_blocklist(blocked_agents={"DemoBlockedAgent"})
    )

    # Build the group chat workflow
    # TODO: Once native middleware support is added to GroupChatBuilder,
    # replace the wrapper below with: .with_message_interceptor(middleware_pipeline)
    workflow = (
        GroupChatBuilder(
            participants=[researcher, writer],
            intermediate_output_from=[researcher, writer],
            orchestrator_agent=orchestrator_agent,
        )
        .with_termination_condition(lambda messages: sum(1 for msg in messages if msg.role == "assistant") >= 4)
        .build()
    )

    task = (
        "What are the key benefits of using async/await in Python? "
        "Provide a concise summary. (Note: Do not include confidential or internal-ip details.)"
    )

    print("\nStarting Group Chat with Agent-Based Manager & Middleware...\n")
    print(f"TASK: {task}\n")
    print("=" * 80)

    # Use the middleware wrapper instead of assuming a builder method
    last_response_id: str | None = None
    async for event in run_with_message_middleware(workflow, task, middleware_pipeline, stream=True):
        if event.type in ("intermediate", "output"):
            data = event.data
            if isinstance(data, AgentResponseUpdate):
                rid = data.response_id
                if rid != last_response_id:
                    if last_response_id is not None:
                        print("\n")
                    print(f"{data.author_name}:", end=" ", flush=True)
                    last_response_id = rid
                print(data.text, end="", flush=True)
            elif event.type == "output":
                outputs = cast(list[Message], data)
                print("\n" + "=" * 80)
                print("\nFinal Conversation Transcript (after middleware):\n")
                for message in outputs:
                    print(f"{message.author_name or message.role}: {message.text}\n")


if __name__ == "__main__":
    asyncio.run(main())