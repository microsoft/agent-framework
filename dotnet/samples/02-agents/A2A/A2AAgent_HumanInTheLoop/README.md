# A2A Agent Human-in-the-Loop

This sample demonstrates a human-in-the-loop pattern with an A2A agent. In the A2A protocol, an agent can pause execution and request additional information from the user by returning an `input-required` task state. The client detects this, prompts the user for input, and sends the response back to the agent to continue the task.

The sample:

- Connects to an A2A agent server specified in the `A2A_AGENT_HOST` environment variable
- Sends an intentionally vague request (e.g., "I'd like to book a flight") to trigger an input request
- Polls using continuation tokens until the agent requests user input or completes the task
- Detects `A2AInputRequestContent` items in the response, prompts the user via the console, and sends responses back using the `CreateResponse` helper method
- Polls again until the task completes and displays the final result

This pattern is essential for building interactive A2A client applications where the remote agent may need to gather additional details from the user during task execution.

# Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10.0 SDK or later
- An A2A agent server running and accessible via HTTP that supports user input requests (the `input-required` task state)

Set the following environment variable:

```powershell
$env:A2A_AGENT_HOST="http://localhost:5000"  # Replace with your A2A agent server host
```
