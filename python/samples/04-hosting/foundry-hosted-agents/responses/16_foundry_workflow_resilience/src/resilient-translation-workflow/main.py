# Copyright (c) Microsoft. All rights reserved.

"""A model-backed translation workflow with durable background execution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agent_framework import Agent, Message, WorkflowBuilder, WorkflowContext, executor
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.responses import ResponsesServerOptions
from azure.identity import DefaultAzureCredential
from typing_extensions import Never

TranslationState = dict[str, Any]
_agents: dict[str, Agent] = {}


def _crash_marker(stage: str) -> Path:
    return Path.home() / ".workflow-resilience-crashes" / f"{stage}.crashed"


def _crash_once(stage: str) -> None:
    """Terminate the host once for this stage within the persistent session home."""
    if os.getenv("WORKFLOW_CRASH_ONCE_PER_STAGE", "true").lower() not in {"1", "true", "yes"}:
        return

    marker = _crash_marker(stage)
    marker.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        print(f"[{stage}] crash marker found; continuing recovered stage", flush=True)
        return

    with os.fdopen(descriptor, "w", encoding="utf-8") as marker_file:
        marker_file.write(f"Intentional crash for {stage}\n")
        marker_file.flush()
        os.fsync(marker_file.fileno())

    print(f"[{stage}] crash marker persisted; terminating host intentionally", flush=True)
    os._exit(70)


def _clear_crash_marker(stage: str) -> None:
    _crash_marker(stage).unlink(missing_ok=True)


async def _translate(stage: str, text: str) -> str:
    response = await _agents[stage].run(text)
    return response.text.strip()


@executor(id="english-to-french")
async def english_to_french(
    messages: list[Message],
    ctx: WorkflowContext[TranslationState, str],
) -> None:
    source = messages[0].text if messages else ""
    _crash_once("english-to-french")
    french = await _translate("english-to-french", source)
    state: TranslationState = {"source": source, "french": french}
    await ctx.yield_output(f"[French]\n{french}")
    await ctx.send_message(state)
    _clear_crash_marker("english-to-french")


@executor(id="french-to-spanish")
async def french_to_spanish(
    state: TranslationState,
    ctx: WorkflowContext[TranslationState, str],
) -> None:
    _crash_once("french-to-spanish")
    spanish = await _translate("french-to-spanish", state["french"])
    state["spanish"] = spanish
    await ctx.yield_output(f"[Spanish]\n{spanish}")
    await ctx.send_message(state)
    _clear_crash_marker("french-to-spanish")


@executor(id="spanish-to-english")
async def spanish_to_english(
    state: TranslationState,
    ctx: WorkflowContext[Never, str],
) -> None:
    _crash_once("spanish-to-english")
    english = await _translate("spanish-to-english", state["spanish"])
    await ctx.yield_output(
        "\n".join((
            f"[Original English]\n{state['source']}",
            f"[French]\n{state['french']}",
            f"[Spanish]\n{state['spanish']}",
            f"[Round-trip English]\n{english}",
        ))
    )
    _clear_crash_marker("spanish-to-english")


def _create_agent(client: FoundryChatClient, *, name: str, instructions: str) -> Agent:
    return Agent(client=client, name=name, instructions=instructions)


def build_workflow() -> Any:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )
    _agents.update({
        "english-to-french": _create_agent(
            client,
            name="english-to-french",
            instructions=(
                "Translate the user's English text into French. "
                "Return only the translation, without explanations or labels."
            ),
        ),
        "french-to-spanish": _create_agent(
            client,
            name="french-to-spanish",
            instructions=(
                "Translate the user's French text into Spanish. "
                "Return only the translation, without explanations or labels."
            ),
        ),
        "spanish-to-english": _create_agent(
            client,
            name="spanish-to-english",
            instructions=(
                "Translate the user's Spanish text into English. "
                "Return only the translation, without explanations or labels."
            ),
        ),
    })

    return (
        WorkflowBuilder(
            start_executor=english_to_french,
            output_from=[spanish_to_english],
            intermediate_output_from=[english_to_french, french_to_spanish],
        )
        .add_chain([english_to_french, french_to_spanish, spanish_to_english])
        .build()
    )


def main() -> None:
    workflow_agent = build_workflow().as_agent(
        name="resilient-translation-workflow",
        description="Durable English to French to Spanish to English translation workflow.",
    )
    server = ResponsesHostServer(
        workflow_agent,
        options=ResponsesServerOptions(resilient_background=True),
    )
    server.run()


if __name__ == "__main__":
    main()
