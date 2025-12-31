# Copyright (c) Microsoft. All rights reserved.

"""
Session storage using Azure Storage and Agent Framework's built-in serialization.
Uses Azurite for local development.
"""

import json
import logging
import os
from typing import Any

from agent_framework import AgentThread
from azure.core.credentials import AzureNamedKeyCredential
from azure.data.tables import TableServiceClient
from azure.storage.blob import BlobServiceClient

# Azurite configuration for local development
ACCOUNT_NAME = "devstoreaccount1"
ACCOUNT_KEY = "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="
BLOB_ENDPOINT = os.environ.get("BLOB_ENDPOINT", "http://127.0.0.1:10000")
TABLE_ENDPOINT = os.environ.get("TABLE_ENDPOINT", f"http://127.0.0.1:10002/{ACCOUNT_NAME}")

TABLE_NAME = "sessions"
CONTAINER_NAME = "threads"


class SessionStorage:
    """Manages session state using Azure Storage and AgentThread serialization."""
    
    def __init__(self):
        """Initialize Azure Storage clients."""
        credential = AzureNamedKeyCredential(ACCOUNT_NAME, ACCOUNT_KEY)
        
        # Initialize Table Storage client with explicit endpoint
        self.table_service = TableServiceClient(
            endpoint=TABLE_ENDPOINT,
            credential=credential
        )
        self.table_client = self.table_service.get_table_client(TABLE_NAME)
        
        # Initialize Blob Storage client with explicit endpoint
        self.blob_service = BlobServiceClient(
            account_url=f"{BLOB_ENDPOINT}/{ACCOUNT_NAME}",
            credential=credential
        )
        self.container_client = self.blob_service.get_container_client(CONTAINER_NAME)
        
        # Create table and container if they don't exist
        try:
            self.table_service.create_table_if_not_exists(TABLE_NAME)
            logging.info(f"Table '{TABLE_NAME}' ready")
        except Exception as e:
            logging.warning(f"Could not create table: {e}")
        
        try:
            self.container_client.create_container()
            logging.info(f"Container '{CONTAINER_NAME}' created")
        except Exception as e:
            if "ContainerAlreadyExists" not in str(e):
                logging.warning(f"Could not create container: {e}")
    
    async def save_thread(self, session_id: str, thread: AgentThread) -> None:
        """Save AgentThread to blob storage using framework serialization."""
        try:
            blob_name = f"{session_id}/thread.json"
            blob_client = self.container_client.get_blob_client(blob_name)
            
            # Use AgentThread's built-in serialization
            thread_state = await thread.serialize()
            thread_json = json.dumps(thread_state, indent=2)
            blob_client.upload_blob(thread_json, overwrite=True)
            
            logging.info(f"Saved thread for session {session_id}")
        except Exception as e:
            logging.error(f"Error saving thread: {e}")
            raise
    
    async def load_thread(self, session_id: str) -> dict[str, Any] | None:
        """Load AgentThread state from blob storage."""
        try:
            blob_name = f"{session_id}/thread.json"
            blob_client = self.container_client.get_blob_client(blob_name)
            
            # Download and deserialize
            blob_data = blob_client.download_blob()
            thread_json = blob_data.readall()
            thread_state = json.loads(thread_json)
            
            logging.info(f"Loaded thread for session {session_id}")
            return thread_state
        except Exception as e:
            if "BlobNotFound" not in str(e):
                logging.error(f"Error loading thread: {e}")
            return None
    
    def save_conversation(self, session_id: str, conversation: list[Any]) -> None:
        """Save conversation list for workflows (simpler than thread serialization)."""
        try:
            blob_name = f"{session_id}/conversation.json"
            blob_client = self.container_client.get_blob_client(blob_name)
            
            conversation_json = json.dumps(conversation, indent=2)
            blob_client.upload_blob(conversation_json, overwrite=True)
            
            logging.info(f"Saved conversation for session {session_id}")
        except Exception as e:
            logging.error(f"Error saving conversation: {e}")
            raise
    
    def load_conversation(self, session_id: str) -> list[Any] | None:
        """Load conversation list for workflows."""
        try:
            blob_name = f"{session_id}/conversation.json"
            blob_client = self.container_client.get_blob_client(blob_name)
            
            blob_data = blob_client.download_blob()
            conversation_json = blob_data.readall()
            conversation = json.loads(conversation_json)
            
            logging.info(f"Loaded conversation for session {session_id}")
            return conversation
        except Exception as e:
            if "BlobNotFound" not in str(e):
                logging.error(f"Error loading conversation: {e}")
            return None
    
    def session_exists(self, session_id: str) -> bool:
        """Check if session exists in table storage."""
        try:
            entity = self.table_client.get_entity(
                partition_key="session",
                row_key=session_id
            )
            return entity is not None
        except Exception:
            return False
    
    def create_session(self, session_id: str, metadata: dict[str, Any] | None = None) -> None:
        """Create a new session entry in table storage."""
        try:
            entity = {
                "PartitionKey": "session",
                "RowKey": session_id,
                **(metadata or {})
            }
            self.table_client.create_entity(entity)
            logging.info(f"Created session {session_id}")
        except Exception as e:
            logging.error(f"Error creating session: {e}")
            raise
    
    def delete_session(self, session_id: str) -> None:
        """Delete session and its thread data."""
        try:
            # Delete table entity
            self.table_client.delete_entity(
                partition_key="session",
                row_key=session_id
            )
            
            # Delete blob
            blob_name = f"{session_id}/thread.json"
            blob_client = self.container_client.get_blob_client(blob_name)
            blob_client.delete_blob()
            
            logging.info(f"Deleted session {session_id}")
        except Exception as e:
            logging.error(f"Error deleting session: {e}")
            raise
