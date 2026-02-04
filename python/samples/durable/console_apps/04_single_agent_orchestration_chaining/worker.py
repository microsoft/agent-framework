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

from agent_framework import AgentResponse, ChatAgent
from agent_framework.azure import AzureOpenAIChatClient, DurableAIAgentOrchestrationContext, DurableAIAgentWorker
from azure.identity import AzureCliCredential, DefaultAzureCredential
from durabletask.task import OrchestrationContext, Task
from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Agent name
WRITER_AGENT_NAME = "WriterAgent"


def create_writer_agent() -> "ChatAgent":
    """Create the Writer agent using Azure OpenAI.
    
    This agent refines short pieces of text, enhancing initial sentences
    and polishing improved versions further.
    
    Returns:
        ChatAgent: The configured Writer agent
    """
    instructions = (
        "You refine short pieces of text. When given an initial sentence you enhance it;\n"
        "when given an improved sentence you polish it further."
    )
    
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        name=WRITER_AGENT_NAME,
        instructions=instructions,
    )


def get_orchestration():
    """Get the orchestration function for this sample.
    
    Returns:
        The orchestration function to register with the worker
    """
    return single_agent_chaining_orchestration


def single_agent_chaining_orchestration(
    context: OrchestrationContext, _: str
) -> Generator[Task[AgentResponse], AgentResponse, str]:
    """Orchestration that runs the writer agent twice on the same thread.
    
    This demonstrates chaining behavior where the output of the first agent run
    becomes part of the input for the second run, all while maintaining the
    conversation context through a shared thread.
    
    Args:
        context: The orchestration context
        _: Input parameter (unused)
        
    Yields:
        Task[AgentRunResponse]: Tasks that resolve to AgentRunResponse
        
    Returns:
        str: The final refined text from the second agent run
    """
    logger.debug("[Orchestration] Starting single agent chaining...")
    
    # Wrap the orchestration context to access agents
    agent_context = DurableAIAgentOrchestrationContext(context)
    
    # Get the writer agent using the agent context
    writer = agent_context.get_agent(WRITER_AGENT_NAME)
    
    # Create a new thread for the conversation - this will be shared across both runs
    writer_thread = writer.get_new_thread()
    
    logger.debug(f"[Orchestration] Created thread: {writer_thread.session_id}")
    
    prompt = "Write a concise inspirational sentence about learning."
    # First run: Generate an initial inspirational sentence
    logger.info("[Orchestration] First agent run: Generating initial sentence about: %s", prompt)
    initial_response = yield writer.run(
        messages=prompt,
        thread=writer_thread,
    )
    logger.info(f"[Orchestration] Initial response: {initial_response.text}")
    
    # Second run: Refine the initial response on the same thread
    improved_prompt = (
        f"Improve this further while keeping it under 25 words: "
        f"{initial_response.text}"
    )
    
    logger.info("[Orchestration] Second agent run: Refining the sentence: %s", improved_prompt)
    refined_response = yield writer.run(
        messages=improved_prompt,
        thread=writer_thread,
    )
    
    logger.info(f"[Orchestration] Refined response: {refined_response.text}")
    
    logger.debug("[Orchestration] Chaining complete")
    return refined_response.text


def get_worker(
    taskhub: str | None = None,
    endpoint: str | None = None,
    log_handler: logging.Handler | None = None
) -> DurableTaskSchedulerWorker:
    """Create a configured DurableTaskSchedulerWorker.
    
    Args:
        taskhub: Task hub name (defaults to TASKHUB env var or "default")
        endpoint: Scheduler endpoint (defaults to ENDPOINT env var or "http://localhost:8080")
        log_handler: Optional logging handler for worker logging
        
    Returns:
        Configured DurableTaskSchedulerWorker instance
    """
    taskhub_name = taskhub or os.getenv("TASKHUB", "default")
    endpoint_url = endpoint or os.getenv("ENDPOINT", "http://localhost:8080")
    
    logger.debug(f"Using taskhub: {taskhub_name}")
    logger.debug(f"Using endpoint: {endpoint_url}")
    
    credential = None if endpoint_url == "http://localhost:8080" else DefaultAzureCredential()
    
    return DurableTaskSchedulerWorker(
        host_address=endpoint_url,
        secure_channel=endpoint_url != "http://localhost:8080",
        taskhub=taskhub_name,
        token_credential=credential,
        log_handler=log_handler
    )


def setup_worker(worker: DurableTaskSchedulerWorker) -> DurableAIAgentWorker:
    """Set up the worker with agents and orchestrations registered.
    
    Args:
        worker: The DurableTaskSchedulerWorker instance
        
    Returns:
        DurableAIAgentWorker with agents and orchestrations registered
    """
    # Wrap it with the agent worker
    agent_worker = DurableAIAgentWorker(worker)
    
    # Create and register the Writer agent
    logger.debug("Creating and registering Writer agent...")
    writer_agent = create_writer_agent()
    agent_worker.add_agent(writer_agent)
    
    logger.debug(f"✓ Registered agent: {writer_agent.name}")
    
    # Register the orchestration function
    logger.debug("Registering orchestration function...")
    worker.add_orchestrator(single_agent_chaining_orchestration)    # type: ignore
    logger.debug(f"✓ Registered orchestration: {single_agent_chaining_orchestration.__name__}")
    
    return agent_worker


async def main():
    """Main entry point for the worker process."""
    logger.debug("Starting Durable Task Single Agent Chaining Worker with Orchestration...")
    
    # Create a worker using the helper function
    worker = get_worker()
    
    # Setup worker with agents and orchestrations
    setup_worker(worker)
    
    logger.debug("Worker is ready and listening for requests...")
    logger.debug("Press Ctrl+C to stop.")
    
    try:
        # Start the worker (this blocks until stopped)
        worker.start()
        
        # Keep the worker running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.debug("Worker shutdown initiated")
    
    logger.debug("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
