# Copyright (c) Microsoft. All rights reserved.

import asyncio
import random
from collections.abc import AsyncIterable, MutableSequence
from typing import Any

from agent_framework import (
    BaseChatClient,
    ChatAgent,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Role,
    TextContent,
)


class SimpleMockChatClient(BaseChatClient):
    """A simple mock chat client for demonstration purposes.
    
    This client simulates responses without calling any real AI service.
    It demonstrates how to implement a custom chat client by extending BaseChatClient
    and implementing the required _inner_get_response() and _inner_get_streaming_response() methods.
    """
    
    OTEL_PROVIDER_NAME: str = "SimpleMockChatClient"
    
    model_name: str = "mock-model-v1"
    response_delay: float = 0.5

    def __init__(
        self,
        *,
        model_name: str = "mock-model-v1",
        response_delay: float = 0.5,
        **kwargs: Any,
    ) -> None:
        """Initialize the SimpleMockChatClient.

        Args:
            model_name: The name of the mock model to simulate.
            response_delay: Delay in seconds before returning responses.
            **kwargs: Additional keyword arguments passed to BaseChatClient.
        """
        super().__init__(model_name=model_name, response_delay=response_delay, **kwargs)

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        """Send a chat request to the mock AI service.

        Args:
            messages: The chat messages to send.
            chat_options: The options for the request.
            **kwargs: Any additional keyword arguments.

        Returns:
            The chat response contents representing the response(s).
        """
        # Simulate processing delay
        await asyncio.sleep(self.response_delay)
        
        # Generate a simple mock response based on the last user message
        response_text = self._generate_mock_response(messages)
        
        response_message = ChatMessage(
            role=Role.ASSISTANT,
            contents=[TextContent(text=response_text)]
        )
        
        return ChatResponse(
            messages=[response_message],
            model_id=self.model_name,
            response_id=f"mock-resp-{random.randint(1000, 9999)}",
        )

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Send a streaming chat request to the mock AI service.

        Args:
            messages: The chat messages to send.
            chat_options: The chat_options for the request.
            **kwargs: Any additional keyword arguments.

        Yields:
            ChatResponseUpdate: The streaming chat message contents.
        """
        # Generate the complete response first
        response_text = self._generate_mock_response(messages)
        
        # Stream the response word by word
        words = response_text.split()
        for i, word in enumerate(words):
            # Add space before word except for the first one
            chunk_text = f" {word}" if i > 0 else word
            
            yield ChatResponseUpdate(
                contents=[TextContent(text=chunk_text)],
                role=Role.ASSISTANT,
                response_id=f"mock-stream-resp-{random.randint(1000, 9999)}",
                ai_model_id=self.model_name,
            )
            
            # Small delay to simulate streaming
            await asyncio.sleep(0.1)

    def _generate_mock_response(self, messages: MutableSequence[ChatMessage]) -> str:
        """Generate a mock response based on the input messages.

        Args:
            messages: The input messages to respond to.

        Returns:
            A mock response string.
        """
        if not messages:
            return "Hello! I'm a mock chat client. How can I help you?"
        
        # Get the last user message
        last_user_message = None
        for message in reversed(messages):
            if message.role == Role.USER:
                last_user_message = message
                break
        
        if not last_user_message or not last_user_message.text:
            return "I received your message, but I couldn't find any text to respond to."
        
        user_text = last_user_message.text.lower()
        
        # Simple keyword-based responses
        if any(greeting in user_text for greeting in ["hello", "hi", "hey"]):
            responses = [
                "Hello there! Nice to meet you.",
                "Hi! How are you doing today?",
                "Hey! What can I help you with?",
            ]
            return random.choice(responses)
        
        if any(question in user_text for question in ["how are you", "how's it going"]):
            responses = [
                "I'm doing great, thank you for asking!",
                "All systems are running smoothly!",
                "I'm functioning perfectly, thanks!",
            ]
            return random.choice(responses)
        
        if any(weather in user_text for weather in ["weather", "temperature", "rain", "sunny"]):
            responses = [
                "I'm sorry, I don't have access to real weather data as I'm a mock client.",
                "For weather information, you'd need to connect to a real weather service.",
                "This is a mock response - I can't actually check the weather!",
            ]
            return random.choice(responses)
        
        if any(math in user_text for math in ["calculate", "math", "+", "-", "*", "/"]):
            return "I'm a simple mock client and can't perform real calculations, but I'd be happy to pretend!"
        
        # Default responses
        responses = [
            f"That's interesting! You mentioned: '{last_user_message.text}'",
            "I understand what you're saying. As a mock client, I can only provide simulated responses.",
            f"Thanks for your message. In a real implementation, I would process: '{last_user_message.text}'",
            "I'm just a demonstration chat client, but I appreciate you testing me!",
        ]
        
        return random.choice(responses)


class EchoingChatClient(BaseChatClient):
    """A chat client that echoes messages back with modifications.
    
    This demonstrates another custom chat client implementation.
    """
    
    OTEL_PROVIDER_NAME: str = "EchoingChatClient"
    
    prefix: str = "Echo:"

    def __init__(self, *, prefix: str = "Echo:", **kwargs: Any) -> None:
        """Initialize the EchoingChatClient.

        Args:
            prefix: Prefix to add to echoed messages.
            **kwargs: Additional keyword arguments passed to BaseChatClient.
        """
        super().__init__(prefix=prefix, **kwargs)

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        """Echo back the user's message with a prefix."""
        if not messages:
            response_text = "No messages to echo!"
        else:
            # Echo the last user message
            last_user_message = None
            for message in reversed(messages):
                if message.role == Role.USER:
                    last_user_message = message
                    break
            
            if last_user_message and last_user_message.text:
                response_text = f"{self.prefix} {last_user_message.text}"
            else:
                response_text = f"{self.prefix} [No text message found]"
        
        response_message = ChatMessage(
            role=Role.ASSISTANT,
            contents=[TextContent(text=response_text)]
        )
        
        return ChatResponse(
            messages=[response_message],
            model_id="echo-model-v1",
            response_id=f"echo-resp-{random.randint(1000, 9999)}",
        )

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Stream back the echoed message character by character."""
        # Get the complete response first
        response = await self._inner_get_response(
            messages=messages, 
            chat_options=chat_options, 
            **kwargs
        )
        
        if response.messages:
            response_text = response.messages[0].text or ""
            
            # Stream character by character
            for char in response_text:
                yield ChatResponseUpdate(
                    contents=[TextContent(text=char)],
                    role=Role.ASSISTANT,
                    response_id=f"echo-stream-resp-{random.randint(1000, 9999)}",
                    ai_model_id="echo-model-v1",
                )
                await asyncio.sleep(0.05)


async def main() -> None:
    """Demonstrates how to implement and use custom chat clients with ChatAgent."""
    print("=== Custom Chat Client Examples ===\n")

    # Example 1: SimpleMockChatClient
    print("--- SimpleMockChatClient Example ---")
    
    # Create the custom chat client
    mock_client = SimpleMockChatClient(
        model_name="my-mock-model",
        response_delay=0.2,  # Faster for demo
    )
    
    # Use the chat client directly
    print("Using chat client directly:")
    direct_response = await mock_client.get_response("Hello, mock client!")
    print(f"Direct response: {direct_response.messages[0].text}")
    
    # Create an agent using the custom chat client
    agent = mock_client.create_agent(
        name="MockAgent",
        instructions="You are a helpful assistant powered by a mock chat client.",
    )
    
    print(f"\nAgent Name: {agent.name}")
    print(f"Agent Display Name: {agent.display_name}")
    
    # Test non-streaming with agent
    query = "How are you doing today?"
    print(f"\nUser: {query}")
    result = await agent.run(query)
    print(f"Agent: {result.messages[0].text}")
    
    # Test streaming with agent
    query2 = "Can you help me with the weather?"
    print(f"\nUser: {query2}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run_stream(query2):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print()

    # Example 2: EchoingChatClient
    print("\n--- EchoingChatClient Example ---")
    
    echo_client = EchoingChatClient(prefix="🔊 Echo:")
    
    # Create agent with the echoing client
    echo_agent = echo_client.create_agent(
        name="EchoAgent",
        instructions="You echo back what users say.",
    )
    
    # Test echoing
    query3 = "This is a test message"
    print(f"\nUser: {query3}")
    result = await echo_agent.run(query3)
    print(f"Agent: {result.messages[0].text}")
    
    # Test streaming echo
    query4 = "Stream this message back to me"
    print(f"\nUser: {query4}")
    print("Agent: ", end="", flush=True)
    async for chunk in echo_agent.run_stream(query4):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print()

    # Example 3: Using with threads and conversation history
    print("\n--- Using Custom Chat Client with Thread ---")
    
    thread = agent.get_new_thread()
    
    # Multiple messages in conversation
    messages = [
        "Hello, I'm starting a conversation",
        "What's 2 + 2?",
        "Thanks for the help!",
    ]
    
    for msg in messages:
        result = await agent.run(msg, thread=thread)
        print(f"User: {msg}")
        print(f"Agent: {result.messages[0].text}\n")
    
    # Check conversation history
    if thread.message_store:
        messages = await thread.message_store.list_messages()
        print(f"Thread contains {len(messages)} messages")
    else:
        print("Thread has no message store configured")

    # Example 4: Custom chat client with ChatAgent parameters
    print("\n--- Custom Chat Client with ChatAgent Options ---")
    
    # Create agent with additional options
    advanced_agent = mock_client.create_agent(
        name="AdvancedMockAgent",
        instructions="You are an advanced assistant with custom settings.",
        # These options will be passed to the underlying chat client
        temperature=0.8,
        max_tokens=100,
    )
    
    query5 = "Tell me something creative"
    print(f"User: {query5}")
    result = await advanced_agent.run(query5)
    print(f"Advanced Agent: {result.messages[0].text}")

    # Example 5: Error handling
    print("\n--- Error Handling Example ---")
    
    try:
        # Create a client that might have issues
        problem_client = SimpleMockChatClient(response_delay=0.1)
        problem_agent = problem_client.create_agent(name="ProblemAgent")
        
        # This should work fine with our mock client
        result = await problem_agent.run("Test error handling")
        print(f"Error handling test passed: {result.messages[0].text}")
        
    except Exception as e:
        print(f"Caught exception: {e}")


if __name__ == "__main__":
    asyncio.run(main())