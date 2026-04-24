# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) workflow demonstrating **multi-agent chaining** and hosted using the **Responses protocol**. It shows how to use the Agent Framework's `WorkflowBuilder` to compose a pipeline of specialized agents — a slogan writer, a legal reviewer, and a formatter — that process a request sequentially. Each agent receives only the output of the previous agent, and only the final formatted result is returned to the caller.

> The workflow will be used as an agent. Read more about Agent Framework workflows in the [Agent Framework documentation](https://learn.microsoft.com/en-us/agent-framework/workflows/) and workflow as an agent in the [Workflow as an Agent documentation](https://learn.microsoft.com/en-us/agent-framework/workflows/as-agents?pivots=programming-language-python).

> This sample requires a more advanced model because the model needs to continue the conversation from an assistant message. Not all models perform well in this scenario. Tested with OpenAI's model `gpt-5.4`.

## How It Works

### Model Integration

The agent creates three specialized `Agent` instances sharing the same `FoundryChatClient`: a **writer** that generates slogans, a **legal reviewer** that ensures compliance, and a **formatter** that styles the output. Each agent is wrapped in an `AgentExecutor` with `context_mode="last_agent"` so it only sees the previous agent's output. The `WorkflowBuilder` wires them into a linear pipeline and limits the output to the formatter's result.

See [main.py](main.py) for the full implementation.

### Agent Hosting

The workflow is exposed as a single agent via `.as_agent()` and hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

## Running the Agent Host

Follow the instructions in the [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally) section of the README in the parent directory to run the agent host.

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the [parent README](../../README.md) for more details. Use this README for sample queries you can send to the agent.

Send a POST request to the server with a JSON body containing a "message" field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Create a slogan for a new electric SUV that is affordable and fun to drive."}'
```

Invoke with `azd`:

```bash
azd ai agent invoke --local "Create a slogan for a new electric SUV that is affordable and fun to drive."
```

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.
