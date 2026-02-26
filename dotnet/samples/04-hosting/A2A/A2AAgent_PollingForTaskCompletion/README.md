# Polling for A2A Agent Task Completion

This sample demonstrates how to poll for long-running task completion using continuation tokens with an A2A AI agent, following the background responses pattern.

The sample:

- Connects to an A2A agent server specified in the `A2A_AGENT_HOST` environment variable
- Sends a request to the agent that may take time to complete
- Polls the agent at regular intervals using continuation tokens until a final response is received
- Displays the final result

This pattern is useful when an AI model cannot complete a complex task in a single response and needs multiple rounds of processing.

# Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10.0 SDK or later
- An A2A agent server running and accessible via HTTP

Set the following environment variable:

```powershell
$env:A2A_AGENT_HOST="http://localhost:5000"  # Replace with your A2A agent server host
```
