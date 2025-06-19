# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import os
import asyncio
from openai import AsyncOpenAI, AsyncAzureOpenAI
from azure.identity import DefaultAzureCredential

from azure.ai.agent.chat_completion_agent import (
    ChatClientAgent,
    ChatClientAgentOptions,
    ChatOptions,
    OpenAIChatClient
)
from azure.ai.agent.common import ChatMessage, ChatRole

async def main():
    """
    Sample demonstrating the use of ChatClientAgent with OpenAI API.
    
    To use this sample, you need to set the following environment variables:
    - OPENAI_API_KEY: Your OpenAI API key if using OpenAI directly
    - AZURE_OPENAI_ENDPOINT: Your Azure OpenAI endpoint URL if using Azure OpenAI
    - AZURE_OPENAI_API_KEY: Your Azure OpenAI API key if using Azure OpenAI with an API key
    
    For Azure OpenAI with Azure AD authentication, no API key is needed, but you need
    to be logged in with Azure CLI or have the appropriate environment variables set
    for the DefaultAzureCredential to work.
    """
    # Choose which provider to use (OpenAI or Azure OpenAI)
    provider = os.environ.get("PROVIDER", "AZURE_OPENAI").upper()
    
    # Create the appropriate client based on the provider
    if provider == "OPENAI":
        # Initialize OpenAI client
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
            
        client = AsyncOpenAI(api_key=api_key)
        model_id = os.environ.get("OPENAI_MODEL_ID", "gpt-4o")
        
    elif provider == "AZURE_OPENAI":
        # Initialize Azure OpenAI client
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        if not endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT environment variable is required")
            
        api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")
        
        if api_key:
            # Use API key authentication
            client = AsyncAzureOpenAI(
                api_key=api_key,
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2023-12-01-preview"),
                azure_endpoint=endpoint
            )
        else:
            # Use Azure AD authentication
            client = AsyncAzureOpenAI(
                azure_ad_token_provider=DefaultAzureCredential(),
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2023-12-01-preview"),
                azure_endpoint=endpoint
            )
            
        model_id = deployment_name or os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
    else:
        raise ValueError(f"Unsupported provider: {provider}")
    
    # Create a chat client
    chat_client = OpenAIChatClient(client)
    
    # Create agent options
    options = ChatClientAgentOptions()
    options.name = "MathTutor"
    options.description = "An AI math tutor that helps students with math problems."
    options.instructions = "You are an AI math tutor. Help students understand math concepts and solve problems."
    
    # Set the model ID in the chat options
    options.chat_options = ChatOptions()
    options.chat_options.model_id = model_id
    
    # Create the agent
    agent = ChatClientAgent(chat_client, options)
    
    # Create a new thread
    thread = agent.get_new_thread()
    
    # Run the agent with a message
    print("Sending message to the agent...")
    response = await agent.run_async_with_message(
        "Can you explain to me how to solve this equation: 2x + 5 = 15?",
        thread=thread
    )
    
    # Print the response
    print("\nAgent response:")
    for message in response.messages:
        print(f"{message.role.value.capitalize()}: {message.content}")

    # Continue the conversation in the same thread
    print("\nSending follow-up message...")
    response = await agent.run_async_with_message(
        "What if the equation was 3x - 7 = 14?",
        thread=thread
    )
    
    # Print the response
    print("\nAgent response:")
    for message in response.messages:
        print(f"{message.role.value.capitalize()}: {message.content}")
        
    # Demonstrate streaming
    print("\nTesting streaming response...")
    print("Question: What is the quadratic formula?")
    
    # Stream the response
    print("\nAgent streaming response:")
    print(f"{ChatRole.ASSISTANT.value.capitalize()}: ", end="", flush=True)
    
    async for update in agent.run_streaming_async_with_message(
        "What is the quadratic formula?",
        thread=thread
    ):
        print(update.content or "", end="", flush=True)
    print()  # Add a newline at the end

if __name__ == "__main__":
    asyncio.run(main())
