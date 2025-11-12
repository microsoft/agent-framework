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

You can also send JSON requests:

```bash
curl -X POST http://localhost:7071/api/agents/Joker/run \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"message": "Tell me a joke about a pirate."}'
```

To continue a conversation, include the `thread_id` in the query string or JSON body:

```bash
curl -X POST "http://localhost:7071/api/agents/Joker/run?thread_id=@dafx-joker@your-thread-id" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"message": "Tell me another one."}'
```

The response from the agent will be displayed in the terminal where you ran `func start`. The expected `text/plain` output will look something like:

```text
Why don't pirates ever learn the alphabet? Because they always get stuck at "C"!
```

The expected `application/json` output will look something like:

```json
{
  "status": 200,
  "thread_id": "@dafx-joker@your-thread-id",
  "response": {
    "Messages": [
      {
        "AuthorName": "Joker",
        "CreatedAt": "2025-11-11T12:00:00.0000000Z",
        "Role": "assistant",
        "Contents": [
          {
            "Type": "text",
            "Text": "Why don't pirates ever learn the alphabet? Because they always get stuck at 'C'!"
          }
        ]
      }
    ],
    "Usage": {
      "InputTokenCount": 78,
      "OutputTokenCount": 36,
      "TotalTokenCount": 114
    }
  }
}
```
