# Workflow

The design goal is to create workflows that can be specified in a declarative
way to allow for easy creation and modification without needing to change the
underlying code. 

## `Workflow` is Agent

A `Workflow` is an agent composed of other agents. It follows the same interface
as an agent. This allows for nested workflows, where a workflow can contain other
workflows.

## Agents in a `Workflow`

Each agent (or a `Workflow`) in a `Workflow` has a thread on which it will
always run. The thread may be privated, or shared among some or all of the agents.

When do agents share a `thread`?

- When an agent is called through handoff or as a tool by another agent, the caller
    agent's thread may be shared with the callee agent.

When do agents not share a `thread`?

- When a set of worker agents are called through a "fan-out" and "fan-in" pattern, where the worker
    agents are called in parallel and the results are combined by an aggregator agent.

Thread sharing can be configured through the `Workflow`'s constructor.
By default, each agent has its own private thread and no sharing.

See [Threads](threads.md) for more details on how threads work.

## `Workflow` from control flow graph

A `Workflow` can be created from a control flow graph of agents.
The graph is a directed graph where each node is an agent and each edge
is a transition between agents. The graph can contain loops
and conditional transitions.

The control flow graph specifies the order in which agents are called
and the conditions under which they are called.

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
```

## `Workflow` from message router

By default, each message is delivered to an _inbox_ of every agent in a `Workflow`.
When an agent is called, the inbox is cleared and the messages are added
to the thread that is used by the agent.

If multiple agents share a thread, each message is added exactly once to the thread.

To customize the message flow, we can configure how each inbox behaves.
Each agent's inbox can be configured to only accept messages from a specific sender(s). 
We can also configure the inbox batch size, time-to-live for messages in the inbox
and various other parameters that controls how the inbox is processed.

The configuration of agents' inboxes is done using a `Router` object,
which can be built using a `RouterBuilder` object.

```python
graph = ...

router = RouterBuilder() \
    .add_route(source=agent1, target=agent2) \ # Agent2 will receive messages from agent1.
    .add_route(source=[agent1, agent2], target=agent3, batch_size=10, ttl="1h") \ # Agent3 will receive messages from agent1 and agent2, with a batch size of 10 and a time-to-live of 1 hour.
    .add_route(source=Router.ANY, target=agent4) \ # Agent4 will receive all messages.
).build()

# Create a workflow from the graph and router.
workflow = Workflow(graph=graph, router=router)
```

You can also skip the graph all together and just create a workflow from the router.
In this case, all agents will run concurrently to process the messages delivered
to their inboxes, according to the inbox rules.

```python
# Create a workflow from the router.
workflow = Workflow(router=router)
```

The validation of the router is done as part of the workflow creation, to ensure
that no gap exists in the routing, and warning for cascading routes.

## Run `Workflow`

It is the same as running an agent.

```python
# Create a message batch to send to the workflow.
# The run context is used to pass in the event channel and other context
# shared by the agents.
thread = [
    Message("Hello"),
    Message("Can you find the file 'foo.txt' for me?"),
]
context = RunContext(event_channel="console")
result = await workflow.run(thread, context=context)
```

## `Workflow` has a final response

A `Workflow` is expected to have a final response, which is the final response in the 
result of the last agent in the workflow. The final response is returned as part of the
`Result` object returned by the `run` method.

This is to ensure the workflow can be used in the same way as an agent. 

## Stopping `Workflow`

A `workflow` may run indefinitely, so it is important to have a way to stop it.

```python
# Use a stopping condition to stop the workflow when the condition is met.
# Detail design TBD.
condition = StopCondition(
    condition=Any(...),
    timeout="1h",
)
workflow = Workflow(graph=graph, stop_condition=condition)
```

TBD.

## `Workflow` can be stateless

The workflow state is kept in the thread object as input to the `run` method.
If not provided, the workflow will create new sub-threads for each agent
in the workflow for their private threads, otherwise, the workflow will
use the provided sub-thread.

```python
# Create a workflow with a graph and router.
workflow = Workflow(graph=graph, router=router, stop_condition=condition)

# Create a new thread.
thread = [
    Message("Hello"),
    Message("Can you find the file 'foo.txt' for me?"),
]

# Run the workflow.
result = await workflow.run(thread, context=context)

# Update the thread with new messages from the user.
thread = result.thread + [
    Message("Can you find the file 'bar.txt' for me?"),
]

# Resume the workflow from where it left off.
result = await workflow.run(thread, context=context)
```

Read more about [Threads](threads.md) for more details on threads.

## Pre-defined workflows

The framework ships with a few pre-defined workflows for common orchestration
patterns. These workflows can be used as-is or as a starting point for
new developers, however, when using them, you should be aware of the underlying
implementation and move on to custom workflows when a limit is reached.

The pre-defined workflows are:
- `Sequential`: A sequential workflow that calls each agent in order,
  its message flow can be configured separately.
- `MapReduce`: A map-reduce workflow that splits a task into smaller
  tasks, runs them in parallel and then combines the results.
- `RoundRobinGroupChat`: agents are called in a round-robin fashion in a loop.
- `SelectorGroupChat`: agents are selected on each iteration by the workflow's built-in
  LLM based selector.
- `Swarm`: use handoffs.

The predefined workflows are implemented as subclasses of the `Workflow` class.