# Deployment

After defining an agent using the `Agent` class, you setup your app in a similar way to a Flask/FastAPI app.

```python
from agent_framework import AgentRuntime

def create_agent(id: str, runtime: AgentRuntime) -> None:
    return MyAgent(id, runtime)

def app(runtime: AgentRuntime) -> None:
    runtime.register_agent("myagent", create_agent)
```

This includes a factory to create agent instances, and an entrypoint that registers all "types" of agents that are hosted in this app.

You might then be able to execute this app like:

```sh
agentrunner --entrypoint myapp:app --state-dir /tmp/agents
```

This would bring up a process and expose some interface that would make this agent accessible. Depending on how `agentrunner` is invoked, perhaps different interfaces are exposed.

## State

State is associated with an agent `id`. The agent id is based on how the agentrunner is invoked. For example, there may be a REST server exposed with the following route:

- `/agents/<agent_type>/<id>/run` - POST

Which will cause an agent to be created with that id, hydrated with the state associated with that id.

## Testing locally

If you wish to use the agent without hosting it within agentrunner, you can use a concrete AgentRuntime implementation to run the agent locally. For example, you can use the `LocalAgentRuntime` class to run an agent in a local process.

```python
from agent_framework import LocalAgentRuntime

# Using in-memory state
runtime = LocalAgentRuntime()

agent = MyAgent("my_id", runtime)
```

## Containerization

Since the app's interface essentially the `AgentRuntime` and the entrypoint, you can containerize the app using a Dockerfile. The entrypoint would be the command to run the agentrunner with the appropriate arguments, or a custom entrypoint can be injected at runtime which uses a different `AgentRuntime` implementation.
