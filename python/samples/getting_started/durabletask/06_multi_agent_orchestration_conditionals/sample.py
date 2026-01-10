"""Multi-Agent Orchestration with Conditionals Sample - Durable Task Integration

This sample demonstrates conditional orchestration logic with two agents:
- SpamDetectionAgent: Analyzes emails for spam content
- EmailAssistantAgent: Drafts professional responses to legitimate emails

The orchestration branches based on spam detection results, calling different
activity functions to handle spam or send legitimate email responses.

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

logging.basicConfig(
    level=logging.INFO,
    force=True
)
logger = logging.getLogger()


def main():
    """Main entry point - runs both worker and client in single process."""
    logger.debug("Starting Durable Task Spam Detection Orchestration Sample (Combined Worker + Client)...")
    
    silent_handler = logging.NullHandler()
    # Create and start the worker using helper function and context manager
    with get_worker(log_handler=silent_handler) as dts_worker:
        # Register agents, orchestrations, and activities using helper function
        setup_worker(dts_worker)
        
        # Start the worker
        dts_worker.start()
        logger.debug("Worker started and listening for requests...")
        
        # Create the client using helper function
        client = get_client(log_handler=silent_handler)
        logger.debug("CLIENT: Starting orchestration tests...")
        
        try:
            # Test 1: Legitimate email
            # logger.info("TEST 1: Legitimate Email")
            
            run_client(
                client,
                email_id="email-001",
                email_content="Hello! I wanted to reach out about our upcoming project meeting scheduled for next week."
            )
                
            # Test 2: Spam email
            logger.info("TEST 2: Spam Email")
            
            run_client(
                client,
                email_id="email-002",
                email_content="URGENT! You've won $1,000,000! Click here now to claim your prize! Limited time offer! Don't miss out!"
            )
            
        except Exception as e:
            logger.exception(f"Error during sample execution: {e}")
        
        logger.debug("Sample completed. Worker shutting down...")


if __name__ == "__main__":
    load_dotenv()
    main()
