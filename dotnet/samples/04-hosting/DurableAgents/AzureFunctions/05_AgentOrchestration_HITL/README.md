# Multi-Agent Orchestration with Human-in-the-Loop Sample

This sample demonstrates how to use the Durable Agent Framework (DAFx) to create a human-in-the-loop (HITL) workflow using a single AI agent. The workflow uses a writer agent to generate content and requires human approval on every iteration, emphasizing the human-in-the-loop pattern.

## Key Concepts Demonstrated

- Single-agent orchestration
- Human-in-the-loop feedback loop using external events (`WaitForExternalEvent`)
- Activity functions for non-agentic workflow steps
- Iterative content refinement based on human feedback
- Custom status tracking for workflow visibility
- Error handling with maximum retry attempts and timeout handling for human approval

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup and function app running, you can test the sample by sending an HTTP request with a topic to start the content generation workflow.

You can use the `demo.http` file to send a topic to the agents, or a command line tool like `curl` as shown below:

Bash (Linux/macOS/WSL):

```bash
curl -X POST http://localhost:7071/api/hitl/run \
    -H "Content-Type: application/json" \
    -d '{
      "topic": "The Future of Artificial Intelligence",
      "max_review_attempts": 3,
      "timeout_minutes": 5
    }'
```

PowerShell:

```powershell
$body = @{
    topic = "The Future of Artificial Intelligence"
    max_review_attempts = 3
    timeout_minutes = 5
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/hitl/run `
    -ContentType application/json `
    -Body $body
```

The response will be a JSON object that looks something like the following, which indicates that the orchestration has started.

```json
{
  "message": "HITL content generation orchestration started.",
  "topic": "The Future of Artificial Intelligence",
  "instanceId": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "statusQueryGetUri": "http://localhost:7071/api/hitl/status/a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
}
```

The orchestration will:

1. Generate initial content using the WriterAgent
2. Notify the user to review the content
3. Wait for human feedback via external event (configurable timeout)
4. If approved by human, publish the content
5. If rejected by human, incorporate feedback and regenerate content
6. If approval timeout occurs, treat as rejection and fail the orchestration
7. Repeat until human approval is received or maximum loop iterations are reached

Once the orchestration is waiting for human approval, you can send approval or rejection using the approval endpoint:

Bash (Linux/macOS/WSL):

```bash
# Approve the content
curl -X POST http://localhost:7071/api/hitl/approve/a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6 \
    -H "Content-Type: application/json" \
    -d '{
      "approved": true,
      "feedback": "Great article! The content is well-structured and informative."
    }'

# Reject the content with feedback
curl -X POST http://localhost:7071/api/hitl/approve/a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6 \
    -H "Content-Type: application/json" \
    -d '{
      "approved": false,
      "feedback": "The article needs more technical depth and better examples."
    }'
```

PowerShell:

```powershell
# Approve the content
Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/hitl/approve/a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6 `
    -ContentType application/json `
    -Body '{ "approved": true, "feedback": "Great article! The content is well-structured and informative." }'

# Reject the content with feedback
Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/hitl/approve/a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6 `
    -ContentType application/json `
    -Body '{ "approved": false, "feedback": "The article needs more technical depth and better examples." }'
```

Once the orchestration has completed, you can get the status by sending a GET request to the `statusQueryGetUri` URL. The response will be a JSON object that looks something like the following:

```json
{
  "failureDetails": null,
  "input": {
    "topic": "The Future of Artificial Intelligence",
    "max_review_attempts": 3
  },
  "instanceId": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "output": {
    "content": "The Future of Artificial Intelligence is..."
  },
  "runtimeStatus": "Completed",
  "workflowStatus": "Content published successfully at 2025-10-15T12:00:00Z"
}
```
