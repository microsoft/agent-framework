"""Single Agent Orchestration Chaining Sample - Durable Task Integration

This sample demonstrates chaining two invocations of the same agent inside a Durable Task
orchestration while preserving the conversation state between runs. The orchestration
runs the writer agent sequentially on a shared thread to refine text iteratively.

Components used:
- AzureOpenAIChatClient to construct the writer agent
- DurableTaskSchedulerWorker and DurableAIAgentWorker for agent hosting
- DurableTaskSchedulerClient and orchestration for sequential agent invocations
- Thread management to maintain conversation context across invocations

Prerequisites: 
- Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME 
  (plus AZURE_OPENAI_API_KEY or Azure CLI authentication)
- Durable Task Scheduler must be running (e.g., using Docker emulator)

To run this sample:
    python sample.py
"""

import asyncio
import json
import logging
import os
from collections.abc import Generator
from typing import Any

from agent_framework import AgentRunResponse
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework_durabletask import DurableAIAgentOrchestrationContext, DurableAIAgentWorker
from azure.identity import AzureCliCredential, DefaultAzureCredential
from dotenv import load_dotenv
from durabletask.task import OrchestrationContext, Task
from durabletask.azuremanaged.client import DurableTaskSchedulerClient
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


async def run_client(
    endpoint: str, taskhub_name: str, credential: DefaultAzureCredential | None
):
    """Run the client to start and monitor the orchestration.
    
    Args:
        endpoint: The durable task scheduler endpoint
        taskhub_name: The task hub name
        credential: The credential for authentication
    """
    logger.info("")
    logger.info("=" * 80)
    logger.info("CLIENT: Starting orchestration...")
    logger.info("=" * 80)
    logger.info("")
    
    # Create a client
    client = DurableTaskSchedulerClient(
        host_address=endpoint,
        secure_channel=endpoint != "http://localhost:8080",
        taskhub=taskhub_name,
        token_credential=credential
    )
    
    try:
        # Start the orchestration
        instance_id = client.schedule_new_orchestration(
            single_agent_chaining_orchestration
        )
        
        logger.info(f"Orchestration started with instance ID: {instance_id}")
        logger.info("Waiting for orchestration to complete...")
        logger.info("")
        
        # Retrieve the final state
        metadata = client.wait_for_orchestration_completion(
            instance_id=instance_id,
            timeout=300
        )
        
        if metadata and metadata.runtime_status.name == "COMPLETED":
            result = metadata.serialized_output
            
            logger.info("")
            logger.info("=" * 80)
            logger.info("ORCHESTRATION COMPLETED SUCCESSFULLY!")
            logger.info("=" * 80)
            logger.info("")
            
            # Parse and display the result
            if result:
                final_text = json.loads(result)
                logger.info("Final refined sentence:")
                logger.info(f"  {final_text}")
            else:
                logger.warning("No output returned from orchestration")
        
        elif metadata:
            logger.error(f"Orchestration did not complete successfully: {metadata.runtime_status.name}")
            if metadata.serialized_output:
                logger.error(f"Output: {metadata.serialized_output}")
        else:
            logger.error("Could not retrieve orchestration metadata")
    
    except Exception as e:
        logger.exception(f"Error during orchestration: {e}")
    
    logger.info("")
    logger.info("Client shutting down")


def main():
    """Main entry point - runs both worker and client in single process."""
    logger.info("Starting Single Agent Orchestration Chaining Sample...")
    logger.info("")
    
    # Load environment variables
    load_dotenv()
    
    # Get environment variables for taskhub and endpoint with defaults
    taskhub_name = os.getenv("TASKHUB", "default")
    endpoint = os.getenv("ENDPOINT", "http://localhost:8080")

    logger.info(f"Using taskhub: {taskhub_name}")
    logger.info(f"Using endpoint: {endpoint}")
    logger.info("")

    # Set credential to None for emulator, or DefaultAzureCredential for Azure
    credential = None if endpoint == "http://localhost:8080" else DefaultAzureCredential()
    secure_channel = endpoint != "http://localhost:8080"
    
    # Create and start the worker using a context manager
    with DurableTaskSchedulerWorker(
        host_address=endpoint,
        secure_channel=secure_channel,
        taskhub=taskhub_name,
        token_credential=credential
    ) as worker:
        
        # Wrap with the agent worker
        agent_worker = DurableAIAgentWorker(worker)
        
        # Create and register the Writer agent
        logger.info("Creating and registering Writer agent...")
        writer_agent = create_writer_agent()
        agent_worker.add_agent(writer_agent)
        
        logger.info(f"✓ Registered agent: {writer_agent.name}")
        logger.info(f"  Entity name: dafx-{writer_agent.name}")
        
        # Register the orchestration function
        logger.info("Registering orchestration function...")
        worker.add_orchestrator(single_agent_chaining_orchestration)
        logger.info("✓ Registered orchestration: single_agent_chaining_orchestration")
        logger.info("")
        
        # Start the worker
        worker.start()
        logger.info("Worker started and listening for requests...")
        logger.info("")
        
        # Run the client in the same process
        try:
            asyncio.run(run_client(endpoint, taskhub_name, credential))
        except KeyboardInterrupt:
            logger.info("Sample interrupted by user")
        finally:
            logger.info("Worker stopping...")
    
    logger.info("Sample completed")


if __name__ == "__main__":
    load_dotenv()
    main()
