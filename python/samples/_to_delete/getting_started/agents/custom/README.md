# Custom Agent and Chat Client Examples

This folder contains examples demonstrating how to implement custom agents and chat clients using the Microsoft Agent Framework.

## Examples

| File | Description |
|------|-------------|
| [`custom_agent.py`](custom_agent.py) | Shows how to create custom agents by extending the `BaseAgent` class. Demonstrates the `EchoAgent` implementation with both streaming and non-streaming responses, proper thread management, and message history handling. |
| [`custom_chat_client.py`](../../chat_client/custom_chat_client.py) | Demonstrates how to create custom chat clients by extending the `BaseChatClient` class. Shows a `EchoingChatClient` implementation and how to integrate it with `ChatAgent` using the `as_agent()` method. |

## Key Takeaways

### Custom Agents
- Custom agents give you complete control over the agent's behavior
- You must implement both `run()` for both the `stream=True` and `stream=False` cases
- Use `self._normalize_messages()` to handle different input message formats
- Use `self._notify_thread_of_new_messages()` to properly manage conversation history

### Custom Chat Clients
- Custom chat clients allow you to integrate any backend service or create new LLM providers
- You must implement `_inner_get_response()` with a stream parameter to handle both streaming and non-streaming responses
- Custom chat clients can be used with `ChatAgent` to leverage all agent framework features
- Use the `as_agent()` method to easily create agents from your custom chat clients

Both approaches allow you to extend the framework for your specific use cases while maintaining compatibility with the broader Agent Framework ecosystem.

## Understanding Raw Client Classes

The framework provides `Raw...Client` classes (e.g., `RawOpenAIChatClient`, `RawOpenAIResponsesClient`, `RawAzureAIClient`) that are intermediate implementations without middleware, telemetry, or function invocation support.

### Warning: Raw Clients Should Not Normally Be Used Directly

**The `Raw...Client` classes should not normally be used directly.** They do not include the middleware, telemetry, or function invocation support that you most likely need. If you do use them, you should carefully consider which additional layers to apply.

### Layer Ordering

There is a defined ordering for applying layers that you should follow:

1. **ChatMiddlewareLayer** - Should be applied **first** because it also prepares function middleware
2. **FunctionInvocationLayer** - Handles tool/function calling loop
3. **ChatTelemetryLayer** - Must be **inside** the function calling loop for correct per-call telemetry
4. **Raw...Client** - The base implementation (e.g., `RawOpenAIChatClient`)

Example of correct layer composition:

```python
class MyCustomClient(
    ChatMiddlewareLayer[TOptions],
    FunctionInvocationLayer[TOptions],
    ChatTelemetryLayer[TOptions],
    RawOpenAIChatClient[TOptions],  # or BaseChatClient for custom implementations
    Generic[TOptions],
):
    """Custom client with all layers correctly applied."""
    pass
```

### Use Fully-Featured Clients Instead

For most use cases, use the fully-featured public client classes which already have all layers correctly composed:

- `OpenAIChatClient` - OpenAI Chat completions with all layers
- `OpenAIResponsesClient` - OpenAI Responses API with all layers
- `AzureOpenAIChatClient` - Azure OpenAI Chat with all layers
- `AzureOpenAIResponsesClient` - Azure OpenAI Responses with all layers
- `AzureAIClient` - Azure AI Project with all layers

These clients handle the layer composition correctly and provide the full feature set out of the box.
