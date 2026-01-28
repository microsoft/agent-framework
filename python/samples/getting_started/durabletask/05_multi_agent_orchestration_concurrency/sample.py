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
    logger.debug("Starting Durable Task Multi-Agent Orchestration Sample (Combined Worker + Client)...")
    
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
        
        # Define the prompt
        prompt = "What is temperature?"
        logger.debug("CLIENT: Starting orchestration...")

        try:
            # Run the client to start the orchestration
            run_client(client, prompt)
        except Exception as e:
            logger.exception(f"Error during sample execution: {e}")
        
        logger.debug("Sample completed. Worker shutting down...")


if __name__ == "__main__":
    load_dotenv()
    main()
