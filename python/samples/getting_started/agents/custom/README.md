# Custom Agent and Chat Client Examples

This folder contains examples demonstrating how to implement custom agents and chat clients using the Microsoft Agent Framework.

## Files

### `custom_agent.py`

This file shows how to create custom agents by extending the `BaseAgent` class. It includes two example implementations:

1. **EchoAgent**: A simple agent that echoes user messages with a customizable prefix
2. **ReversalAgent**: An agent that reverses the text of user messages

**Key concepts demonstrated:**
- Extending `BaseAgent` 
- Implementing required `run()` and `run_stream()` methods
- Working with `AgentRunResponse` and `AgentRunResponseUpdate`
- Handling both streaming and non-streaming responses
- Managing conversation threads and message history

### `custom_chat_client.py`

This file demonstrates how to create custom chat clients by extending the `BaseChatClient` class. It includes two example implementations:

1. **SimpleMockChatClient**: A mock client that simulates AI responses without calling real services
2. **EchoingChatClient**: A client that echoes messages back with a prefix

**Key concepts demonstrated:**
- Extending `BaseChatClient`
- Implementing required `_inner_get_response()` and `_inner_get_streaming_response()` methods  
- Working with `ChatResponse` and `ChatResponseUpdate`
- Creating agents using custom chat clients via `create_agent()`
- Using custom chat clients with `ChatAgent`

## Running the Examples

To run these examples:

```bash
# Run the custom agent example
python custom_agent.py

# Run the custom chat client example  
python custom_chat_client.py
```

## Key Takeaways

### Custom Agents
- Custom agents give you complete control over the agent's behavior
- You must implement both `run()` (for complete responses) and `run_stream()` (for streaming responses)
- Use `self._normalize_messages()` to handle different input message formats
- Use `self._notify_thread_of_new_messages()` to properly manage conversation history

### Custom Chat Clients
- Custom chat clients allow you to integrate any backend service or create mock implementations
- You must implement both `_inner_get_response()` and `_inner_get_streaming_response()`
- Custom chat clients can be used with `ChatAgent` to leverage all agent framework features
- Use the `create_agent()` method to easily create agents from your custom chat clients

Both approaches allow you to extend the framework for your specific use cases while maintaining compatibility with the broader Agent Framework ecosystem.