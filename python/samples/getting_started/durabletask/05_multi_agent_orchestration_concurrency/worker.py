"""Worker process for hosting multiple agents with orchestration using Durable Task.

This worker registers two domain-specific agents (physicist and chemist) and an orchestration
function that runs them concurrently. The orchestration uses OrchestrationAgentExecutor 
to execute agents in parallel and aggregate their responses.

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
from durabletask.task import OrchestrationContext, when_all, Task
from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Agent names
PHYSICIST_AGENT_NAME = "PhysicistAgent"
CHEMIST_AGENT_NAME = "ChemistAgent"


def create_physicist_agent():
    """Create the Physicist agent using Azure OpenAI.
    
    Returns:
        AgentProtocol: The configured Physicist agent
    """
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        name=PHYSICIST_AGENT_NAME,
        instructions="You are an expert in physics. You answer questions from a physics perspective.",
    )


def create_chemist_agent():
    """Create the Chemist agent using Azure OpenAI.
    
    Returns:
        AgentProtocol: The configured Chemist agent
    """
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        name=CHEMIST_AGENT_NAME,
        instructions="You are an expert in chemistry. You answer questions from a chemistry perspective.",
    )


def multi_agent_concurrent_orchestration(context: OrchestrationContext, prompt: str) -> Generator[Task[Any], Any, dict[str, str]]:
    """Orchestration that runs both agents in parallel and aggregates results.
    
    Uses DurableAIAgentOrchestrationContext to wrap the orchestration context and
    access agents via the OrchestrationAgentExecutor.
    
    Args:
        context: The orchestration context
        
    Returns:
        dict: Dictionary with 'physicist' and 'chemist' response texts
    """
    
    logger.info(f"[Orchestration] Starting concurrent execution for prompt: {prompt}")
    
    # Wrap the orchestration context to access agents
    agent_context = DurableAIAgentOrchestrationContext(context)
    
    # Get agents using the agent context (returns DurableAIAgent proxies)
    physicist = agent_context.get_agent(PHYSICIST_AGENT_NAME)
    chemist = agent_context.get_agent(CHEMIST_AGENT_NAME)
    
    # Create separate threads for each agent
    physicist_thread = physicist.get_new_thread()
    chemist_thread = chemist.get_new_thread()
    
    logger.info(f"[Orchestration] Created threads - Physicist: {physicist_thread.session_id}, Chemist: {chemist_thread.session_id}")
    
    # Create tasks from agent.run() calls - these return DurableAgentTask instances
    physicist_task = physicist.run(messages=str(prompt), thread=physicist_thread)
    chemist_task = chemist.run(messages=str(prompt), thread=chemist_thread)
    
    logger.info("[Orchestration] Created agent tasks, executing concurrently...")
    
    # Execute both tasks concurrently using when_all
    # The DurableAgentTask instances wrap the underlying entity calls
    task_results = yield when_all([physicist_task, chemist_task])
    
    logger.info("[Orchestration] Both agents completed")
    
    # Extract results from the tasks - DurableAgentTask yields AgentRunResponse
    physicist_result: AgentRunResponse = task_results[0]
    chemist_result: AgentRunResponse = task_results[1]
    
    result = {
        "physicist": physicist_result.text,
        "chemist": chemist_result.text,
    }
    
    logger.info(f"[Orchestration] Aggregated results ready")
    return result


async def main():
    """Main entry point for the worker process."""
    logger.info("Starting Durable Task Multi-Agent Worker with Orchestration...")
    
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
    
    # Create and register both agents
    logger.info("Creating and registering agents...")
    physicist_agent = create_physicist_agent()
    chemist_agent = create_chemist_agent()
    
    agent_worker.add_agent(physicist_agent)
    agent_worker.add_agent(chemist_agent)
    
    logger.info(f"✓ Registered agent: {physicist_agent.name}")
    logger.info(f"  Entity name: dafx-{physicist_agent.name}")
    logger.info(f"✓ Registered agent: {chemist_agent.name}")
    logger.info(f"  Entity name: dafx-{chemist_agent.name}")
    logger.info("")
    
    # Register the orchestration function
    logger.info("Registering orchestration function...")
    worker.add_orchestrator(multi_agent_concurrent_orchestration)
    logger.info(f"✓ Registered orchestration: {multi_agent_concurrent_orchestration.__name__}")
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
