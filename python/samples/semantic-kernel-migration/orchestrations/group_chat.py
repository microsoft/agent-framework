# Copyright (c) Microsoft. All rights reserved.

"""Side-by-side group chat orchestrations for Agent Framework and Semantic Kernel."""

import asyncio
import sys
from collections.abc import Sequence
from typing import Any, cast

from agent_framework import ChatAgent, ChatMessage, GroupChatBuilder, WorkflowOutputEvent
from agent_framework.azure import AzureOpenAIChatClient, AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from semantic_kernel.agents import Agent, ChatCompletionAgent, GroupChatOrchestration
from semantic_kernel.agents.orchestration.group_chat import (
    BooleanResult,
    GroupChatManager,
    MessageResult,
    StringResult,
)
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.connectors.ai.prompt_execution_settings import PromptExecutionSettings
from semantic_kernel.contents import AuthorRole, ChatHistory, ChatMessageContent
from semantic_kernel.functions import KernelArguments
from semantic_kernel.kernel import Kernel
from semantic_kernel.prompt_template import KernelPromptTemplate, PromptTemplateConfig

if sys.version_info >= (3, 12):
    from typing import override  # pragma: no cover
else:
    from typing_extensions import override  # pragma: no cover


DISCUSSION_TOPIC = "What are the essential steps for launching a community hackathon?"


######################################################################
# Semantic Kernel orchestration path
######################################################################


def build_semantic_kernel_agents() -> list[Agent]:
    credential = AzureCliCredential()

    researcher = ChatCompletionAgent(
        name="Researcher",
        description="Collects background information and potential resources.",
        instructions=(
            "Gather concise facts or considerations that help plan a community hackathon. "
            "Keep your responses factual and scannable."
        ),
        service=AzureChatCompletion(credential=credential),
    )

    planner = ChatCompletionAgent(
        name="Planner",
        description="Synthesizes an actionable plan from available notes.",
        instructions=(
            "Use the running conversation to draft a structured action plan. Emphasize logistics and sequencing."
        ),
        service=AzureChatCompletion(credential=credential),
    )

    return [researcher, planner]


class ChatCompletionGroupChatManager(GroupChatManager):
    """Group chat manager that delegates orchestration decisions to an Azure OpenAI deployment."""

    service: ChatCompletionClientBase
    topic: str

    termination_prompt: str = (
        "You are coordinating a conversation about '{{topic}}'. "
        "Decide if the discussion has produced a solid answer. "
        'Respond using JSON: {"result": true|false, "reason": "..."}.'
    )

    selection_prompt: str = (
        "You are coordinating a conversation about '{{topic}}'. "
        "Choose the next participant by returning JSON with keys (result, reason). "
        "The result must match one of: {{participants}}."
    )

    summary_prompt: str = (
        "You have just finished a discussion about '{{topic}}'. "
        "Summarize the plan and highlight key takeaways. Return JSON with keys (result, reason) where "
        "result is the final response text."
    )

    def __init__(self, *, topic: str, service: ChatCompletionClientBase) -> None:
        super().__init__(topic=topic, service=service)
        self._round_robin_index = 0

    async def _render_prompt(self, template: str, **kwargs: Any) -> str:
        prompt_template = KernelPromptTemplate(prompt_template_config=PromptTemplateConfig(template=template))
        return await prompt_template.render(Kernel(), arguments=KernelArguments(**kwargs))

    @override
    async def should_request_user_input(self, chat_history: ChatHistory) -> BooleanResult:
        return BooleanResult(result=False, reason="This orchestration is fully automated.")

    @override
    async def should_terminate(self, chat_history: ChatHistory) -> BooleanResult:
        rendered_prompt = await self._render_prompt(self.termination_prompt, topic=self.topic)
        chat_history.messages.insert(
            0,
            ChatMessageContent(role=AuthorRole.SYSTEM, content=rendered_prompt),
        )
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content="Decide if the discussion is complete."),
        )

        response = await self.service.get_chat_message_content(
            chat_history,
            settings=PromptExecutionSettings(response_format=BooleanResult),
        )
        result = BooleanResult.model_validate_json(response.content)
        return result

    @override
    async def select_next_agent(
        self,
        chat_history: ChatHistory,
        participant_descriptions: dict[str, str],
    ) -> StringResult:
        rendered_prompt = await self._render_prompt(
            self.selection_prompt,
            topic=self.topic,
            participants=", ".join(participant_descriptions.keys()),
        )
        chat_history.messages.insert(
            0,
            ChatMessageContent(role=AuthorRole.SYSTEM, content=rendered_prompt),
        )
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content="Pick the next participant to speak."),
        )

        response = await self.service.get_chat_message_content(
            chat_history,
            settings=PromptExecutionSettings(response_format=StringResult),
        )
        result = StringResult.model_validate_json(response.content)
        if result.result not in participant_descriptions:
            raise RuntimeError(f"Unknown participant selected: {result.result}")
        return result

    @override
    async def filter_results(self, chat_history: ChatHistory) -> MessageResult:
        rendered_prompt = await self._render_prompt(self.summary_prompt, topic=self.topic)
        chat_history.messages.insert(
            0,
            ChatMessageContent(role=AuthorRole.SYSTEM, content=rendered_prompt),
        )
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content="Summarize the plan."),
        )

        response = await self.service.get_chat_message_content(
            chat_history,
            settings=PromptExecutionSettings(response_format=StringResult),
        )
        string_result = StringResult.model_validate_json(response.content)
        return MessageResult(
            result=ChatMessageContent(role=AuthorRole.ASSISTANT, content=string_result.result),
            reason=string_result.reason,
        )


async def sk_agent_response_callback(message: ChatMessageContent | Sequence[ChatMessageContent]) -> None:
    if isinstance(message, ChatMessageContent):
        messages: Sequence[ChatMessageContent] = [message]
    elif isinstance(message, Sequence) and not isinstance(message, (str, bytes)):
        messages = list(message)
    else:
        messages = [cast(ChatMessageContent, message)]

    for item in messages:
        print(f"# {item.name}\n{item.content}\n")


async def run_semantic_kernel_example(task: str) -> str:
    credential = AzureCliCredential()
    orchestration = GroupChatOrchestration(
        members=build_semantic_kernel_agents(),
        manager=ChatCompletionGroupChatManager(
            topic=DISCUSSION_TOPIC,
            service=AzureChatCompletion(credential=credential),
            max_rounds=8,
        ),
        agent_response_callback=sk_agent_response_callback,
    )

    runtime = InProcessRuntime()
    runtime.start()

    try:
        orchestration_result = await orchestration.invoke(task=task, runtime=runtime)
        final_message = await orchestration_result.get(timeout=30)
        if isinstance(final_message, ChatMessageContent):
            return final_message.content or ""
        return str(final_message)
    finally:
        await runtime.stop_when_idle()


######################################################################
# Agent Framework orchestration path
######################################################################


async def run_agent_framework_example(task: str) -> str:
    credential = AzureCliCredential()

    researcher = ChatAgent(
        name="Researcher",
        description="Collects background information and potential resources.",
        instructions=(
            "Gather concise facts or considerations that help plan a community hackathon. "
            "Keep your responses factual and scannable."
        ),
        chat_client=AzureOpenAIChatClient(credential=credential),
    )

    planner = ChatAgent(
        name="Planner",
        description="Turns the collected notes into a concrete action plan.",
        instructions=("Propose a structured action plan that accounts for logistics, roles, and timeline."),
        chat_client=AzureOpenAIResponsesClient(credential=credential),
    )

    workflow = (
        GroupChatBuilder()
        .with_orchestrator(agent=AzureOpenAIChatClient(credential=credential).as_agent())
        .participants([researcher, planner])
        .build()
    )

    final_response = ""
    async for event in workflow.run_stream(task):
        if isinstance(event, WorkflowOutputEvent):
            data = event.data
            if isinstance(data, list) and len(data) > 0:
                # Get the final message from the conversation
                final_message = data[-1]
                final_response = final_message.text or "" if isinstance(final_message, ChatMessage) else str(data)
            else:
                final_response = str(data)
    return final_response


async def main() -> None:
    task = "Kick off the group discussion."

    print("===== Agent Framework Group Chat =====")
    af_response = await run_agent_framework_example(task)
    print(af_response or "No response returned.")
    print()

    print("===== Semantic Kernel Group Chat =====")
    sk_response = await run_semantic_kernel_example(task)
    print(sk_response or "No response returned.")


if __name__ == "__main__":
    asyncio.run(main())
