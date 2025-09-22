# Custom Agent and Chat Client Examples

This folder contains examples demonstrating how to implement custom agents and chat clients using the Microsoft Agent Framework.

## Examples

| File | Description |
|------|-------------|
| [`custom_agent.py`](custom_agent.py) | Shows how to create custom agents by extending the `BaseAgent` class. Demonstrates the `EchoAgent` implementation with both streaming and non-streaming responses, proper thread management, and message history handling. |
| [`custom_chat_client.py`](custom_chat_client.py) | Demonstrates how to create custom chat clients by extending the `BaseChatClient` class. Shows the `EchoingChatClient` implementation and how to integrate it with `ChatAgent` using the `create_agent()` method. |

## Key Takeaways

### Custom Agents
- Custom agents give you complete control over the agent's behavior
- You must implement both `run()` (for complete responses) and `run_stream()` (for streaming responses)
- Use `self._normalize_messages()` to handle different input message formats
- Use `self._notify_thread_of_new_messages()` to properly manage conversation history

### Custom Chat Clients
- Custom chat clients allow you to integrate any backend service or create new LLM providers
- You must implement both `_inner_get_response()` and `_inner_get_streaming_response()`
- Custom chat clients can be used with `ChatAgent` to leverage all agent framework features
- Use the `create_agent()` method to easily create agents from your custom chat clients

Both approaches allow you to extend the framework for your specific use cases while maintaining compatibility with the broader Agent Framework ecosystem.