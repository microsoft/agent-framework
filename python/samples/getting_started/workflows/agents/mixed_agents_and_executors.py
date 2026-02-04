# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Never

from agent_framework import (
    AgentExecutorResponse,
    ChatAgent,
    Executor,
    HostedCodeInterpreterTool,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    tool,
)
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential

"""
This sample demonstrates how to create a workflow that combines an AI agent executor
with a custom executor.

The workflow consists of two stages:
1. An AI agent with code interpreter capabilities that generates and executes Python code
2. An evaluator executor that reviews the agent's output and provides a final assessment

Key concepts demonstrated:
- Creating an AI agent with tool capabilities (HostedCodeInterpreterTool)
- Building workflows using WorkflowBuilder with an agent and a custom executor
- Using the @handler decorator in the executor to process AgentExecutorResponse from the agent
- Connecting workflow executors with edges to create a processing pipeline
- Yielding final outputs from terminal executors
- Non-streaming workflow execution and result collection

Prerequisites:
- Azure AI services configured with required environment variables
- Azure CLI authentication (run 'az login' before executing)
- Basic understanding of async Python and workflow concepts
"""


class Evaluator(Executor):
    """Custom executor that evaluates the output from an AI agent.

    This executor demonstrates how to:
    - Create a custom workflow executor that processes agent responses
    - Use the @handler decorator to define the processing logic
    - Access agent execution details including response text and usage metrics
    - Yield final results to complete the workflow execution

    The evaluator checks if the agent successfully generated the Fibonacci sequence
    and provides feedback on correctness along with resource consumption details.
    """

    @handler
    async def handle(self, message: AgentExecutorResponse, ctx: WorkflowContext[Never, str]) -> None:
        """Evaluate the agent's response and complete the workflow with a final assessment.

        This handler:
        1. Receives the AgentExecutorResponse containing the agent's complete interaction
        2. Checks if the expected Fibonacci sequence appears in the response text
        3. Extracts usage details (token consumption, execution time, etc.)
        4. Yields a final evaluation string to complete the workflow

        Args:
            message: The response from the Azure AI agent containing text and metadata
            ctx: Workflow context for yielding the final output string
        """
        target_text = "1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89"
        correctness = target_text in message.agent_response.text
        consumption = message.agent_response.usage_details
        await ctx.yield_output(f"Correctness: {correctness}, Consumption: {consumption}")


def create_coding_agent(client: AzureAIAgentClient) -> ChatAgent:
    """Create an AI agent with code interpretation capabilities.

    This agent can generate and execute Python code to solve problems.

    Args:
        client: The AzureAIAgentClient used to create the agent

    Returns:
        A ChatAgent configured with coding instructions and tools
    """
    return client.as_agent(
        name="CodingAgent",
        instructions=("You are a helpful assistant that can write and execute Python code to solve problems."),
        tools=HostedCodeInterpreterTool(),
    )


async def main():
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(credential=credential) as chat_client,
    ):
        # Build a workflow: Agent generates code -> Evaluator assesses results
        # The agent will be wrapped in a special agent executor which produces AgentExecutorResponse
        workflow = (
            WorkflowBuilder()
            .register_agent(lambda: create_coding_agent(chat_client), name="coding_agent")
            .register_executor(lambda: Evaluator(id="evaluator"), name="evaluator")
            .set_start_executor("coding_agent")
            .add_edge("coding_agent", "evaluator")
            .build()
        )

        # Execute the workflow with a specific coding task
        results = await workflow.run(
            "Generate the fibonacci numbers to 100 using python code, show the code and execute it."
        )

        # Extract and display the final evaluation
        outputs = results.get_outputs()
        if isinstance(outputs, list) and len(outputs) == 1:
            print("Workflow results:", outputs[0])
        else:
            raise ValueError("Unexpected workflow outputs:", outputs)


if __name__ == "__main__":
    asyncio.run(main())
