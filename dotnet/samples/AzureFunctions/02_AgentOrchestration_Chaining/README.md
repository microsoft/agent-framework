# Single Agent Orchestration Sample

This sample demonstrates how to use the Durable Agent Framework (DAFx) to create a simple Azure Functions app that orchestrates sequential calls to a single AI agent using the same conversation thread for context continuity.

## Key Concepts Demonstrated

- Orchestrating multiple interactions with the same agent in a deterministic order
- Using the same `AgentThread` across multiple calls to maintain conversational context
- Durable orchestration with automatic checkpointing and resumption from failures
- HTTP API integration for starting and monitoring orchestrations

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup and function app running, you can test the sample by sending an HTTP request to start the orchestration.

You can use the `demo.http` file to start the orchestration, or a command line tool like `curl` as shown below:

Bash (Linux/macOS/WSL):

```bash
curl -X POST http://localhost:7071/api/singleagent/run
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:7071/api/singleagent/run
```

The response will be a JSON object that looks something like the following, which indicates that the orchestration has started.

```json
{
  "message": "Single-agent orchestration started.",
  "instanceId": "86313f1d45fb42eeb50b1852626bf3ff",
  "statusQueryGetUri": "http://localhost:7071/api/singleagent/status/86313f1d45fb42eeb50b1852626bf3ff"
}
```

The orchestration will proceed to run the WriterAgent twice in sequence:

1. First, it writes an inspirational sentence about learning
2. Then, it refines the initial output using the same conversation thread

Once the orchestration has completed, you can get the status of the orchestration by sending a GET request to the `statusQueryGetUri` URL. The response will be a JSON object that looks something like the following:

```json
{
    "failureDetails": null,
    "input": null,
    "instanceId": "86313f1d45fb42eeb50b1852626bf3ff",
    "output": "Learning serves as the key, opening doors to boundless opportunities and a brighter future.",
    "runtimeStatus": "Completed"
}
```
