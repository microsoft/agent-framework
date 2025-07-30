# Guardrails

The design goal is to provide a flexible and extensible way to implement guardrails
and a built-in set of guardrails that can be used for common use cases.

> NOTE: this is work in progress.

Guardrails can be template-based to adapt to different input data types, which
include:
- `Message` for agent messages.
- `ToolCall` for tool call requests.
- `ToolResult` for tool call results.

Guardrails are added to other components such as `ModelClient` and `MCPServer`
as hooks that are called before and after the main logic of the component.

For example, the `ModelClient` has methods to add input and output guardrails.

```python
model_client = ModelClient(...)
model_client.add_input_guardrails([
    PIIGuardrail[Message](...),
    SensitiveDataGuardrail[Message](...),
])
model_client.add_output_guardrails([
    HarmfulContentGuardrail[Message](...),
])
```

Another example to show how to use a guardrail with an MCP server:

```python
guardrail = PIIGuardrail(
    config={
        "rules": [
            {
                "type": "email",
                "action": "block"
            },
            {
                "type": "phone",
                "action": "block"
            }
        ]
    }
)

mcp_server = MCPServer(...)
mcp_server.add_output_guardrail(guardrail)
```