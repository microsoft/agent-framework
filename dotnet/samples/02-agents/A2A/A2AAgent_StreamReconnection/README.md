# A2A Agent Stream Reconnection

This sample demonstrates how to reconnect to an A2A agent's streaming response using continuation tokens, allowing recovery from stream interruptions without losing progress.

The sample:

- Connects to an A2A agent server specified in the `A2A_AGENT_HOST` environment variable
- Sends a request to the agent and begins streaming the response
- Captures a continuation token from the stream for later reconnection
- Simulates a stream interruption by breaking out of the streaming loop
- Reconnects to the same response stream using the captured continuation token
- Displays the response received after reconnection

This pattern is useful when network interruptions or other failures may disrupt an ongoing streaming response, and you need to recover and continue processing.

> **Note:** Continuation tokens are only available when the underlying A2A agent returns a task. If the agent returns a message instead, the continuation token will not be initialized and stream reconnection is not applicable.

# Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10.0 SDK or later
- An A2A agent server running and accessible via HTTP

Set the following environment variable:

```powershell
$env:A2A_AGENT_HOST="http://localhost:5000"  # Replace with your A2A agent server host
```
