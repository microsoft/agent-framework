"""Multi-Agent Orchestration Sample - Durable Task Integration (Combined Worker + Client)

This sample demonstrates running both the worker and client in a single process for
concurrent multi-agent orchestration. The worker registers two domain-specific agents
(physicist and chemist) and an orchestration function that runs them in parallel.

The orchestration uses OrchestrationAgentExecutor to execute agents concurrently
and aggregate their responses.

Prerequisites: 
- Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME 
  (plus AZURE_OPENAI_API_KEY or Azure CLI authentication)
- Durable Task Scheduler must be running (e.g., using Docker)

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
from durabletask.task import OrchestrationContext, when_all, Task
from durabletask.azuremanaged.client import DurableTaskSchedulerClient
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
    
    # Execute both tasks concurrently using task.when_all
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


async def run_client(endpoint: str, taskhub_name: str, credential: DefaultAzureCredential | None, prompt: str):
    """Run the client to start and monitor the orchestration.
    
    Args:
        endpoint: The durable task scheduler endpoint
        taskhub_name: The task hub name
        credential: The credential for authentication
        prompt: The prompt to send to both agents
    """
    logger.info("")
    logger.info("=" * 80)
    logger.info("CLIENT: Starting orchestration...")
    logger.info("=" * 80)
    
    # Create a client
    client = DurableTaskSchedulerClient(
        host_address=endpoint,
        secure_channel=endpoint != "http://localhost:8080",
        taskhub=taskhub_name,
        token_credential=credential
    )
    
    logger.info(f"Prompt: {prompt}")
    logger.info("")
    
    try:
        # Start the orchestration with the prompt as input
        instance_id = client.schedule_new_orchestration(
            multi_agent_concurrent_orchestration,
            input=prompt,
        )
        
        logger.info(f"Orchestration started with instance ID: {instance_id}")
        logger.info("Waiting for orchestration to complete...")
        logger.info("")
        
        # Retrieve the final state
        metadata = client.wait_for_orchestration_completion(
            instance_id=instance_id
        )
        
        if metadata and metadata.runtime_status.name == "COMPLETED":
            result = metadata.serialized_output
            
            logger.info("")
            logger.info("=" * 80)
            logger.info("ORCHESTRATION COMPLETED SUCCESSFULLY!")
            logger.info("=" * 80)
            logger.info("")
            logger.info(f"Prompt: {prompt}")
            logger.info("")
            logger.info("Results:")
            logger.info("")
            
            # Parse and display the result
            if result:
                result_dict = json.loads(result)
            
                logger.info("Physicist's response:")
                logger.info(f"  {result_dict.get('physicist', 'N/A')}")
                logger.info("")
                
                logger.info("Chemist's response:")
                logger.info(f"  {result_dict.get('chemist', 'N/A')}")
                logger.info("")
            
            logger.info("=" * 80)
            
        elif metadata:
            logger.error(f"Orchestration ended with status: {metadata.runtime_status.name}")
            if metadata.serialized_output:
                logger.error(f"Output: {metadata.serialized_output}")
        else:
            logger.error("Orchestration did not complete within the timeout period")
        
    except Exception as e:
        logger.exception(f"Error during orchestration: {e}")


def main():
    """Main entry point - runs both worker and client in single process."""
    logger.info("Starting Durable Task Multi-Agent Orchestration Sample (Combined Worker + Client)...")
    
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
        
        # Start the worker
        worker.start()
        logger.info("Worker started and listening for requests...")
        
        # Define the prompt
        prompt = "What is temperature?"
        
        try:
            # Run the client to start the orchestration
            asyncio.run(run_client(endpoint, taskhub_name, credential, prompt))
            
        except Exception as e:
            logger.exception(f"Error during sample execution: {e}")
        
        logger.info("")
        logger.info("Sample completed. Worker shutting down...")


if __name__ == "__main__":
    load_dotenv()
    main()
