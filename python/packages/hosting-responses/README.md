# agent-framework-hosting-responses

OpenAI Responses-shaped channel for `agent-framework-hosting`.

Exposes a single `POST /responses` endpoint that accepts the OpenAI
Responses API request body and returns either a Responses-shaped JSON
body or a Server-Sent-Events stream when `stream=True`.

```python
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from agent_framework_hosting import AgentFrameworkHost
from agent_framework_hosting_responses import ResponsesChannel

agent = ChatAgent(name="Assistant", chat_client=OpenAIChatClient())

host = AgentFrameworkHost(target=agent, channels=[ResponsesChannel()])
host.serve(port=8000)
```

The base host plumbing lives in
[`agent-framework-hosting`](https://pypi.org/project/agent-framework-hosting/).
