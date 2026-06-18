# Long Running Tools Sample

This sample demonstrates how to use the durable agents extension to create a console app with agents that have long running tools. This sample builds on the [05_AgentOrchestration_HITL](../05_AgentOrchestration_HITL) sample by adding a publisher agent that can start and manage content generation workflows. A key difference is that the publisher agent knows the IDs of the workflows it starts, so it can check the status of the workflows and approve or reject them without being explicitly given the context (instance IDs, etc).

## Key Concepts Demonstrated

The same key concepts as the [05_AgentOrchestration_HITL](../05_AgentOrchestration_HITL) sample are demonstrated, but with the following additional concepts:

- **Long running tools**: Using `DurableAgentContext.Current` to start orchestrations from tool calls
- **Multi-agent orchestration**: Agents can start and manage workflows that orchestrate other agents
- **Human-in-the-loop (with delegation)**: The agent acts as an intermediary between the human and the workflow. The human remains in the loop, but delegates to the agent to start the workflow and approve or reject the content.

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

With the environment setup, you can run the sample:

```bash
cd dotnet/samples/04-hosting/DurableAgents/ConsoleApps/06_LongRunningTools
dotnet run --framework net10.0
```

The app will prompt you for input. You can interact with the Publisher agent:

```text
=== Long Running Tools Sample ===
Enter a topic for the Publisher agent to write about (or 'exit' to quit):

You: Start a content generation workflow for the topic 'The Future of Artificial Intelligence'
Publisher: The content generation workflow for the topic "The Future of Artificial Intelligence" has been successfully started, and the instance ID is **6a04276e8d824d8d941e1dc4142cc254**. If you need any further assistance or updates on the workflow, feel free to ask!
```

Behind the scenes, the publisher agent will:

1. Start the content generation workflow via a tool call
2. The workflow will generate initial content using the Writer agent and wait for human approval, which will be visible in the terminal

Once the workflow is waiting for human approval, you can send approval or rejection by prompting the publisher agent accordingly.

> [!NOTE]
> You must press Enter after each message to continue the conversation. The sample is set up this way because the workflow is running in the background and may write to the console asynchronously.

To tell the agent to rewrite the content with feedback, you can prompt it to reject the content with feedback.

```text
You: Reject the content with feedback: The article needs more technical depth and better examples.
Publisher: The content has been successfully rejected with the feedback: "The article needs more technical depth and better examples." The workflow will now generate new content based on this feedback.
```

Once you're satisfied with the content, you can approve it for publishing.

```text
You: Approve the content
Publisher: The content has been successfully approved for publishing. If you need any more assistance or have further requests, feel free to let me know!
```

Once the workflow has completed, you can get the status by prompting the publisher agent to give you the status.

```text
You: Get the status of the workflow you previously started
Publisher: The status of the workflow with instance ID **6a04276e8d824d8d941e1dc4142cc254** is as follows:

- **Execution Status:** Completed
- **Created At:** December 22, 2025, 23:08:13 UTC
- **Last Updated At:** December 22, 2025, 23:09:59 UTC
- **Workflow Status:** 
  - Message: Content published successfully at December 22, 2025, 23:09:59 UTC
  - Human Feedback: Approved
```

## Viewing Agent and Orchestration State

You can view the state of both the agent and the orchestrations it starts in the Durable Task Scheduler dashboard:

1. Open your browser and navigate to `http://localhost:8082`
2. In the dashboard, you can see:
   - **Agents**: View the state of the Publisher agent, including its conversation history and tool call history
   - **Orchestrations**: View the content generation orchestration instances that were started by the agent via tool calls, including their runtime status, custom status, input, output, and execution history

When the publisher agent starts a workflow, the orchestration instance ID is included in the agent's response. You can use this ID to find the specific orchestration in the dashboard and inspect:

- The orchestration's execution progress
- When it's waiting for human approval (visible in custom status)
- The content generation workflow state
- The WriterAgent state within the orchestration

This demonstrates how agents can manage long-running workflows and how you can monitor both the agent's state and the workflows it orchestrates.
