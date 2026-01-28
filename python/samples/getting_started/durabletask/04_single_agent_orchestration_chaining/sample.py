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

import logging

from dotenv import load_dotenv

# Import helper functions from worker and client modules
from client import get_client, run_client
from worker import get_worker, setup_worker

# Configure logging
logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)


def main():
    """Main entry point - runs both worker and client in single process."""
    logger.debug("Starting Single Agent Orchestration Chaining Sample...")
    
    silent_handler = logging.NullHandler()
    # Create and start the worker using helper function and context manager
    with get_worker(log_handler=silent_handler) as dts_worker:
        # Register agents and orchestrations using helper function
        setup_worker(dts_worker)
        
        # Start the worker
        dts_worker.start()
        logger.debug("Worker started and listening for requests...")
        
        # Create the client using helper function
        client = get_client(log_handler=silent_handler)
        
        logger.debug("CLIENT: Starting orchestration...")
        
        # Run the client in the same process
        try:
            run_client(client)
        except KeyboardInterrupt:
            logger.debug("Sample interrupted by user")
        except Exception as e:
            logger.exception(f"Error during orchestration: {e}")
        finally:
            logger.debug("Worker stopping...")
    
    logger.debug("")
    logger.debug("Sample completed")


if __name__ == "__main__":
    load_dotenv()
    main()
