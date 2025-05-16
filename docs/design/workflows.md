# Workflows

Pesudo Python code for creating a `GraphWorkflow`.

```python
from agent_framework import GraphWorkflow, GraphBuilder, ChatCompletionAgent, Any, All

agent1 = ChatCompletionAgent(
    model_client="OpenAIChatCompletionClient",
    mcp_servers=["MCPServer1", "MCPServer2"],
    memory="ListMemory",
)

agent2 = ChatCompletionAgent(
    model_client="OpenAIChatCompletionClient",
    mcp_servers=["MCPServer3", "MCPServer4"],
    memory="ListMemory",
)

graph = GraphBuilder() \
    .add_agent(agent1) \
    .add_agent(agent2) \
    .add_loop(agent1, agent1, conditions=Any(...)) \
    .add_transition(agent1, agent2, conditions=Any(..., All(...))]) \
    .build()

workflow = GraphWorkflow(graph=graph)

# This is just a teaser, we still need to define how the actual API looks like.
events = workflow.run_stream(
    input_message="Hello, world!",
    context={
        "user_id": "123456",
        "session_id": "abcdefg"
    },
    mcp_servers=["MCPServer1", "MCPServer2", "MCPServer3", "MCPServer4"],
)
```