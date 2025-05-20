# Workflow

The design goal is to create workflows that can be specified in a declarative
way to allow for easy creation and modification without needing to change the
underlying code. Also, workflows should be able to run completely locally or
in a distributed agent runtime, with the same developer experience.

## `Workflow` is Agent

A `Workflow` is an agent composed of other agents. It follows the same interface
as an agent. This allows for nested workflows, where a workflow can contain other
workflows.

## Run `Workflow`

This is the experience of creating a `Workflow` with agent instances directly.

```python
# Create agent instances.
agent1 = MCPAgent(
    model_client="OpenAIChatCompletionClient",
    mcp_server=["MCPServer1", "MCPServer2"],
)
agent2 = MCPAgent(
    model_client="OpenAIChatCompletionClient",
    mcp_server=["MCPServer3", "MCPServer4"],
)
agent3 = MCPAgent(
    model_client="OpenAIChatCompletionClient",
    mcp_server="MCPServer5",
)

# Create a directed graph of agents with conditional loops and transitions.
# The graph builder validates the graph.
graph = GraphBuilder() \
    .add_agent(agent1) \
    .add_agent(agent2) \
    .add_agent(agent3) \
    .add_loop(agent1, agent2, conditions=Any(...)) \
    .add_transition(agent2, agent3, conditions=Any(..., All(...))]) \
    .build()

# Create a workflow from the graph.
workflow = Workflow(graph=graph)

# Create a message batch to send to the workflow.
# The run context is used to pass in the event channel and other context
# shared by the agents.
task = MessageBatch(messages=[...])
context = RunContext(event_channel="console")
result = workflow.run(task=task, context=context)
```

## Run `Workflow` on agent runtime

The agents in a workflow can be hosted on an agent runtime, which may contain
local or remote agents.

```python
# Register agents with the agent runtime.
# These steps may be done separately from the workflow creation.
runtime.register(MCPAgent, config={
    "model_client": {
        "type": "OpenAIChatCompletionClient",
        "model": "gpt-4.1",
    }
    "mcp_server": [{
        "type": "MCPServer",
        ...,
    },
    {
        "type": "MCPServer",
        ...,
    }],
}, type_name="agent1")
runtime.register(MCPAgent, config=..., type_name="agent2")
runtime.register(MCPAgent, config=..., type_name="agent3")

# Get the agent stubs from the agent runtime.
agent1_stub = runtime.get("agent1/123", class=MCPAgent)
agent2_stub = runtime.get("agent2/123", class=MCPAgent)
agent3_stub = runtime.get("agent3/123", class=MCPAgent)

# Create a directed graph of agents with conditional loops and transitions.
# This step is the same as the previous example.
graph = GraphBuilder() \
    .add_agent(agent1_stub) \
    .add_agent(agent2_stub) \
    .add_agent(agent3_stub) \
    .add_loop(agent1_stub, agent2_stub, conditions=Any(...)) \
    .add_transition(agent2_stub, agent3_stub, conditions=Any(..., All(...))]) \
    .build()

# Create a workflow from the graph.
workflow = Workflow(graph=graph)

# The rest is the same as the previous example.
```

The workflow itself may be run on the agent runtime as well.
We need to register the workflow with the agent runtime.

```python
# Create a graph with only agent type information.
# For each agent, the key is optional: if provided, the exact agent instance
# will be used. If not provided, the agent runtime will create a new agent
# with the same key as the workflow's key.
graph = GraphBuilder() \
    .add_agent("agent1", class=MCPAgent, key="123") \
    .add_agent("agent2", class=MCPAgent) \
    .add_agent("agent3", class=MCPAgent) \
    .add_loop("agent1/123", "agent2", conditions=Any(...)) \
    .add_transition("agent2", "agent3", conditions=Any(..., All(...))]) \
    .build()

# Register the workflow with the agent runtime.
runtime.register(Workflow, config={
    "graph": graph,
}, type_name="workflow1")

# Get the workflow stub from the agent runtime.
workflow_stub = runtime.get("workflow1/xyz", class=Workflow)

# The rest is the same as the previous example.
```

## Message flow in `Workflow`

By default, each message is delivered to an "inbox" of every agent in a `Workflow`,
if the agent's input message type matches the message type (i.e., subclasses
the message type). The messages in the "inbox" are then converted into a
`MessageBatch` and passed to the agent's `run` method.

> NOTE: the input message type can be a union of different message types. In
> this case, the message is checked against each type in the union and if
> it matches any of them, it is delivered to the agent.

To customize the message flow, we can configure how the "inbox" behaves.
Each agent's inbox can be configured to only accept messages of a specific type 
and/or from a specific sender(s). 
We can also configure the inbox batch size, time-to-live for messages in the inbox
and various other parameters that controls how the inbox is processed.
This requires a separate configuration step besides the graph.

```python
graph = ...

router = RouterBuilder() \
    .add_route(source="agent1", target="agent2", from_type=MessageType1) \
    .add_route(source=["agent1", "agent2"], target="agent3", batch_size=10, ttl="1h") \
    .add_route(target="agent4", from_type=MessageType3 | MessageType4) \
).build()

# Create a workflow from the graph and router.
workflow = Workflow(graph=graph, router=router)
```

You can also skip the graph all together and just create a workflow from the router.
In this case, all agents will run concurrently to process the messages delivered
to their inboxes, according to the routing rules.

```python
# Create a workflow from the router.
workflow = Workflow(router=router)
```

The validation of the router is done as part of the workflow creation, to ensure
that no gap exists in the routing, and warning for cascading routes.