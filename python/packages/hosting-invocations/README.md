# agent-framework-hosting-invocations

Minimal `POST /invocations` channel for [agent-framework-hosting](../hosting). Useful
for smoke-testing, durable-task drivers, and bespoke clients that don't speak
the OpenAI Responses protocol.

## Wire shape

```
POST /invocations
{
    "message": "hello",
    "session_id": "user-42",
    "stream": false
}
```

Non-streaming response: `{"response": "...", "session_id": "..."}`.
Streaming response: `text/event-stream` of `data:` lines, terminated by
`data: [DONE]`.

## Usage

```python
from agent_framework_hosting import AgentFrameworkHost
from agent_framework_hosting_invocations import InvocationsChannel

host = AgentFrameworkHost(target=my_agent, channels=[InvocationsChannel()])
host.serve()
```
