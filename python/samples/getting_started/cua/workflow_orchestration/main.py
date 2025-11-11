# Copyright (c) Microsoft. All rights reserved.

"""Workflow orchestration example showing Agent Framework + Cua synergies."""

import asyncio
import logging

from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from computer import Computer

from agent_framework_cua import CuaAgentMiddleware, CuaChatClient

logger = logging.getLogger(__name__)


async def main():
    """Run a multi-agent workflow: Research → Cua Automation → Verification."""

    # Step 1: Research Agent (Pure Agent Framework)
    logger.info("📚 Step 1: Research Agent")
    research_agent = ChatAgent(
        chat_client=OpenAIChatClient(model_id="gpt-4o-mini"),
        instructions=(
            "You are a research assistant. Create a detailed automation plan. "
            "For the given task, break it down into specific, actionable steps "
            "that can be automated on a desktop."
        ),
    )

    task = "Find the latest release version of Python from python.org"
    research_response = await research_agent.run(f"Create an automation plan for: {task}")
    logger.info("📋 Research Plan:\n%s", research_response)

    # Step 2: Cua Automation Agent (Agent Framework Orchestration + Cua Execution)
    logger.info("\n🤖 Step 2: Cua Automation Agent")
    async with Computer(
        os_type="linux",
        provider_type="docker",
        image="trycua/cua-xfce:latest",
    ) as computer:
        # Create Cua chat client
        cua_chat_client = CuaChatClient(
            model="anthropic/claude-sonnet-4-5-20250929",
        )

        # Create middleware
        cua_middleware = CuaAgentMiddleware(
            computer=computer,
            require_approval=True,  # Human-in-the-loop via Agent Framework
            approval_interval=3,
        )

        # Create automation agent
        automation_agent = ChatAgent(
            chat_client=cua_chat_client,
            middleware=[cua_middleware],
        )

        # Agent Framework manages the thread and context
        thread = automation_agent.get_new_thread()
        automation_prompt = f"Execute this plan:\n{research_response}\n\nTask: {task}"
        automation_response = await automation_agent.run(automation_prompt, thread)
        logger.info("✅ Automation Result:\n%s", automation_response)

    # Step 3: Verification Agent (Pure Agent Framework)
    logger.info("\n🔍 Step 3: Verification Agent")
    verify_agent = ChatAgent(
        chat_client=OpenAIChatClient(model_id="gpt-4o"),
        instructions=(
            "You are a verification assistant. Analyze the automation results "
            "and confirm if the task was completed successfully. Extract key findings."
        ),
    )

    verification_prompt = f"""
    Original Task: {task}

    Research Plan:
    {research_response}

    Automation Results:
    {automation_response}

    Verify if the task was completed and summarize findings.
    """

    final_result = await verify_agent.run(verification_prompt)
    logger.info("📊 Final Verification:\n%s", final_result)

    return final_result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    result = asyncio.run(main())
    print(f"\n{'='*60}\n🎉 Workflow Complete!\n{'='*60}\n{result}")
