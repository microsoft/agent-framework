"""Worker process for hosting a single agent with chaining orchestration using Durable Task.

This worker registers a writer agent and an orchestration function that demonstrates
chaining behavior by running the agent twice sequentially on the same thread,
preserving conversation context between invocations.

Prerequisites: 
- Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME 
  (plus AZURE_OPENAI_API_KEY or Azure CLI authentication)
- Start a Durable Task Scheduler (e.g., using Docker)
"""

import asyncio
from collections.abc import Generator
import logging
import os
from typing import Any

from agent_framework import AgentRunResponse
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework_durabletask import DurableAIAgentOrchestrationContext, DurableAIAgentWorker
from azure.identity import AzureCliCredential, DefaultAzureCredential
from durabletask.task import OrchestrationContext, Task
from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Agent name
WRITER_AGENT_NAME = "WriterAgent"


def create_writer_agent():
    """Create the Writer agent using Azure OpenAI.
    
    This agent refines short pieces of text, enhancing initial sentences
    and polishing improved versions further.
    
    Returns:
        AgentProtocol: The configured Writer agent
    """
    instructions = (
        "You refine short pieces of text. When given an initial sentence you enhance it;\n"
        "when given an improved sentence you polish it further."
    )
    
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        name=WRITER_AGENT_NAME,
        instructions=instructions,
    )


def single_agent_chaining_orchestration(
    context: OrchestrationContext, _: str
) -> Generator[Task[Any], Any, str]:
    """Orchestration that runs the writer agent twice on the same thread.
    
    This demonstrates chaining behavior where the output of the first agent run
    becomes part of the input for the second run, all while maintaining the
    conversation context through a shared thread.
    
    Args:
        context: The orchestration context
        _: Input parameter (unused)
        
    Returns:
        str: The final refined text from the second agent run
    """
    logger.info("[Orchestration] Starting single agent chaining...")
    
    # Wrap the orchestration context to access agents
    agent_context = DurableAIAgentOrchestrationContext(context)
    
    # Get the writer agent using the agent context
    writer = agent_context.get_agent(WRITER_AGENT_NAME)
    
    # Create a new thread for the conversation - this will be shared across both runs
    writer_thread = writer.get_new_thread()
    
    logger.info(f"[Orchestration] Created thread: {writer_thread.session_id}")
    
    # First run: Generate an initial inspirational sentence
    logger.info("[Orchestration] First agent run: Generating initial sentence...")
    initial_response: AgentRunResponse = yield writer.run(
        messages="Write a concise inspirational sentence about learning.",
        thread=writer_thread,
    )
    logger.info(f"[Orchestration] Initial response: {initial_response.text}")
    
    # Second run: Refine the initial response on the same thread
    improved_prompt = (
        f"Improve this further while keeping it under 25 words: "
        f"{initial_response.text}"
    )
    
    logger.info("[Orchestration] Second agent run: Refining the sentence...")
    refined_response: AgentRunResponse = yield writer.run(
        messages=improved_prompt,
        thread=writer_thread,
    )
    
    logger.info(f"[Orchestration] Refined response: {refined_response.text}")
    
    logger.info("[Orchestration] Chaining complete")
    return refined_response.text


async def main():
    """Main entry point for the worker process."""
    logger.info("Starting Durable Task Single Agent Chaining Worker with Orchestration...")
    
    # Get environment variables for taskhub and endpoint with defaults
    taskhub_name = os.getenv("TASKHUB", "default")
    endpoint = os.getenv("ENDPOINT", "http://localhost:8080")

    logger.info(f"Using taskhub: {taskhub_name}")
    logger.info(f"Using endpoint: {endpoint}")

    # Set credential to None for emulator, or DefaultAzureCredential for Azure
    credential = None if endpoint == "http://localhost:8080" else DefaultAzureCredential()
    
    # Create a worker using Azure Managed Durable Task
    worker = DurableTaskSchedulerWorker(
        host_address=endpoint,
        secure_channel=endpoint != "http://localhost:8080",
        taskhub=taskhub_name,
        token_credential=credential
    )
    
    # Wrap it with the agent worker
    agent_worker = DurableAIAgentWorker(worker)
    
    # Create and register the Writer agent
    logger.info("Creating and registering Writer agent...")
    writer_agent = create_writer_agent()
    agent_worker.add_agent(writer_agent)
    
    logger.info(f"✓ Registered agent: {writer_agent.name}")
    logger.info(f"  Entity name: dafx-{writer_agent.name}")
    logger.info("")
    
    # Register the orchestration function
    logger.info("Registering orchestration function...")
    worker.add_orchestrator(single_agent_chaining_orchestration)
    logger.info(f"✓ Registered orchestration: {single_agent_chaining_orchestration.__name__}")
    logger.info("")
    
    logger.info("Worker is ready and listening for requests...")
    logger.info("Press Ctrl+C to stop.")
    logger.info("")
    
    try:
        # Start the worker (this blocks until stopped)
        worker.start()
        
        # Keep the worker running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Worker shutdown initiated")
    
    logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
