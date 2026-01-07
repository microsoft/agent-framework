"""Human-in-the-Loop Orchestration Sample - Durable Task Integration

This sample demonstrates the HITL pattern with a WriterAgent that generates content
and waits for human approval. The orchestration handles:
- External event waiting (approval/rejection)
- Timeout handling
- Iterative refinement based on feedback
- Activity functions for notifications and publishing

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
from client import get_client, run_interactive_client
from worker import get_worker, setup_worker

logging.basicConfig(
    level=logging.INFO,
    force=True
)
logger = logging.getLogger()


def main():
    """Main entry point - runs both worker and client in single process."""
    logger.debug("Starting Durable Task HITL Content Generation Sample (Combined Worker + Client)...")
    
    silent_handler = logging.NullHandler()
    # Create and start the worker using helper function and context manager
    with get_worker(log_handler=silent_handler) as dts_worker:
        # Register agent, orchestration, and activities using helper function
        setup_worker(dts_worker)
        
        # Start the worker
        dts_worker.start()
        logger.debug("Worker started and listening for requests...")
        
        # Create the client using helper function
        client = get_client(log_handler=silent_handler)
        
        try:
            logger.debug("CLIENT: Starting orchestration tests...")
            
            run_interactive_client(client)
            
        except Exception as e:
            logger.exception(f"Error during sample execution: {e}")
        
        logger.debug("Sample completed. Worker shutting down...")


if __name__ == "__main__":
    load_dotenv()
    main()
