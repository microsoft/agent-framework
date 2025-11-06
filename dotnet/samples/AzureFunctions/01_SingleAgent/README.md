# Single Agent Sample

This sample demonstrates how to use the Durable Agent Framework (DAFx) to create a simple Azure Functions app that hosts a single AI agent and provides direct HTTP API access for interactive conversations.

## Key Concepts Demonstrated

- Using the Microsoft Agent Framework to define a simple AI agent with a name and instructions.
- Registering agents with the Function app and running them using HTTP.
- Conversation management (via session IDs) for isolated interactions.

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup and function app running, you can test the sample by sending an HTTP request to the agent endpoint.

You can use the `demo.http` file to send a message to the agent, or a command line tool like `curl` as shown below:

Bash (Linux/macOS/WSL):

```bash
curl -X POST http://localhost:7071/api/agents/Joker/run \
    -H "Content-Type: text/plain" \
    -d "Tell me a joke about a pirate."
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/agents/Joker/run `
    -ContentType text/plain `
    -Body "Tell me a joke about a pirate."
```

The response from the agent will be displayed in the terminal where you ran `func start`. The expected output will look something like:

```text
Why don't pirates ever learn the alphabet? Because they always get stuck at "C"!
```
