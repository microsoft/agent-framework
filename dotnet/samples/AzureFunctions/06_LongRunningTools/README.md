# Long Running Tools Sample

This sample demonstrates how to use the Durable Agent Framework (DAFx) to create agents with long running tools. This sample builds on the [05_AgentOrchestration_HITL](../05_AgentOrchestration_HITL) sample by adding a publisher agent that can start and manage content generation workflows. A key difference is that the publisher agent knows the IDs of the workflows it starts, so it can check the status of the workflows and approve or reject them without being explicitly given the context (instance IDs, etc).

## Key Concepts Demonstrated

The same key concepts as the [05_AgentOrchestration_HITL](../05_AgentOrchestration_HITL) sample are demonstrated, but with the following additional concepts:

- **Long running tools**: Using `DurableAgentContext.Current` to start orchestrations from tool calls
- **Multi-agent orchestration**: Agents can start and manage workflows that orchestrate other agents
- **Human-in-the-loop (with delegation)**: The agent acts as an intermediary between the human and the workflow. The human remains in the loop, but delegates to the agent to start the workflow and approve or reject the content.

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup and function app running, you can test the sample by sending an HTTP request to start the agent, which will then trigger the content generation workflow.

You can use the `demo.http` file to send requests to the agent, or a command line tool like `curl` as shown below.

Bash (Linux/macOS/WSL):

```bash
curl -i -X POST http://localhost:7071/api/agents/publisher/run \
    -D headers.txt \
    -H "Content-Type: text/plain" \
    -d 'Start a content generation workflow for the topic \"The Future of Artificial Intelligence\"'

# Save the thread ID to a variable and print it to the terminal
threadId=$(cat headers.txt | grep "x-ms-thread-id" | cut -d' ' -f2)
echo "Thread ID: $threadId"
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post `
    -Uri http://localhost:7071/api/agents/publisher/run `
    -ResponseHeadersVariable ResponseHeaders `
    -ContentType text/plain `
    -Body 'Start a content generation workflow for the topic \"The Future of Artificial Intelligence\"' `

# Save the thread ID to a variable and print it to the console
$threadId = $ResponseHeaders['x-ms-thread-id']
Write-Host "Thread ID: $threadId"
```

The response will be a text string that looks something like the following, indicating that the agent request has been received and will be processed:

```http
HTTP/1.1 200 OK
Content-Type: text/plain
x-ms-thread-id: @publisher@351ec855-7f4d-4527-a60d-498301ced36d

The content generation workflow for the topic "The Future of Artificial Intelligence" has been successfully started, and the instance ID is **6a04276e8d824d8d941e1dc4142cc254**. If you need any further assistance or updates on the workflow, feel free to ask!
```

The `x-ms-thread-id` response header contains the thread ID, which can be used to continue the conversation by passing it as a query parameter (`thread_id`) to the `run` endpoint. The commands above show how to save the thread ID to a `$threadId` variable for use in subsequent requests.

Behind the scenes, the publisher agent will:

1. Start the content generation workflow via a tool call
1. The workflow will generate initial content using the Writer agent and wait for human approval, which will be visible in the logs

Once the workflow is waiting for human approval, you can send approval or rejection by prompting the publisher agent accordingly (e.g. "Approve the content" or "Reject the content with feedback: The article needs more technical depth and better examples."):

Bash (Linux/macOS/WSL):

```bash
# Approve the content
curl -X POST "http://localhost:7071/api/agents/publisher/run?thread_id=$threadId" \
    -H "Content-Type: text/plain" \
    -d 'Approve the content'

# Reject the content with feedback
curl -X POST "http://localhost:7071/api/agents/publisher/run?thread_id=$threadId" \
    -H "Content-Type: text/plain" \
    -d 'Reject the content with feedback: The article needs more technical depth and better examples.'
```

PowerShell:

```powershell
# Approve the content
Invoke-RestMethod -Method Post `
    -Uri "http://localhost:7071/api/agents/publisher/run?thread_id=$threadId" `
    -ContentType text/plain `
    -Body 'Approve the content'

# Reject the content with feedback
Invoke-RestMethod -Method Post `
    -Uri "http://localhost:7071/api/agents/publisher/run?thread_id=$threadId" `
    -ContentType text/plain `
    -Body 'Reject the content with feedback: The article needs more technical depth and better examples.'
```

Once the workflow has completed, you can get the status by prompting the publisher agent to give you the status.

Bash (Linux/macOS/WSL):

```bash
curl -X POST "http://localhost:7071/api/agents/publisher/run?thread_id=$threadId" \
    -H "Content-Type: text/plain" \
    -d 'Get the status of the workflow you previously started'
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post `
    -Uri "http://localhost:7071/api/agents/publisher/run?thread_id=$threadId" `
    -ContentType text/plain `
    -Body 'Get the status of the workflow you previously started'
```

The response from the publisher agent will look something like the following:

```text
The status of the workflow with instance ID **ab1076d6e7ec49d8a2c2474d09b69ded** is as follows:

- **Execution Status:** Completed
- **Workflow Status:** Content published successfully at `2025-10-24T20:42:02`
- **Created At:** `2025-10-24T20:41:40.7531781+00:00`
- **Last Updated At:** `2025-10-24T20:42:02.1410736+00:00`

The content has been successfully published.
```
