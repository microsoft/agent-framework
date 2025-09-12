# Microsoft Agent Framework Workflows: Working with Agents

This page provides an overview of how to use **Agents** within the Microsoft Agent Framework Workflows.

## Overview

To add intelligence to your workflows, you can leverage AI agents as part of your workflow execution. AI agents can be easily integrated into workflows, allowing you to create complex, intelligent solutions that were previously difficult to achieve.

::: zone pivot="programming-language-csharp"

## Add an Agent Directly to a Workflow

You can add an agent to your workflow via a edge:

```csharp
// Create the agents first
AIAgent agentA = new ChatClientAgent(chatClient, instructions);
AIAgent agentB = new ChatClientAgent(chatClient, instructions);

// Build a workflow with the agents
WorkflowBuilder builder = new(agentA);
builder.AddEdge(agentA, agentB);
Workflow<ChatMessage> workflow = builder.Build<ChatMessage>();
```

### Running the Workflow

Inside the workflow created above, the agents are actually wrapped inside an executor that handles the communication of the agent with other parts of the workflow. The executor can handle three message types:

- `ChatMessage`: A single chat message
- `List<ChatMessage>`: A list of chat messages
- `TurnToken`: A turn token that signals the start of a new turn

The executor doesn't trigger the agent to respond until it receives a `TurnToken`. Any messages received before the `TurnToken` are buffered and sent to the agent when the `TurnToken` is received.

```csharp
StreamingRun run = await InProcessExecution.StreamAsync(workflow, new ChatMessage(ChatRole.User, "Hello World!"));
// Must send the turn token to trigger the agents. The agents are wrapped as executors.
// When they receive messages, they will cache the messages and only start processing
// when they receive a TurnToken. The turn token will be passed from one agent to the next.
await run.TrySendMessageAsync(new TurnToken(emitEvents: true));
await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
{
    // The agents will run in streaming mode and an AgentRunUpdateEvent
    // will be emitted as new chunks are generated.
    if (evt is AgentRunUpdateEvent agentRunUpdate)
    {
        Console.WriteLine($"{agentRunUpdate.ExecutorId}: {agentRunUpdate.Data}");
    }
}
```

::: zone-end

::: zone pivot="programming-language-python"

## Using the Built-in Agent Executor

Coming soon...

::: zone-end

## Using a Custom Agent Executor

Sometimes you may want to customize how AI agents are integrated into a workflow. You can achieve this by creating a custom executor. This allows you to control:

- The invocation of the agent: streaming or non-streaming
- The message types the agent will handle, including custom message types
- The life cycle of the agent, including initialization and cleanup
- The usage of agent threads and other resources
- Additional events emitted during the agent's execution, including custom events
- Integration with other workflow features, such as shared states and requests/responses

::: zone pivot="programming-language-csharp"

```csharp
internal sealed class CustomAgentExecutor : ReflectingExecutor<CustomAgentExecutor>, IMessageHandler<CustomInput, CustomOutput>
{
    private readonly AIAgent _agent;

    /// <summary>
    /// Creates a new instance of the <see cref="CustomAgentExecutor"/> class.
    /// </summary>
    /// <param name="agent">The AI agent used for custom processing</param>
    public CustomAgentExecutor(AIAgent agent) : base("CustomAgentExecutor")
    {
        this._agent = agent;
    }

    public async ValueTask<CustomOutput> HandleAsync(CustomInput message, IWorkflowContext context)
    {
        // Retrieve any shared states if needed
        var sharedState = await context.ReadStateAsync<SharedStateType>("sharedStateId", scopeName: "SharedStateScope");

        // Render the input for the agent
        var agentInput = RenderInput(message, sharedState);
 
        // Invoke the agent
        // Assume the agent is configured with structured outputs with type `CustomOutput`
        var response = await this._agent.RunAsync(agentInput);
        var customOutput = JsonSerializer.Deserialize<CustomOutput>(response.Text);

        return customOutput;
    }
}
```

::: zone-end

::: zone pivot="programming-language-python"

Coming soon...

::: zone-end

## Next Steps

- [Learn how to use workflows as agents](./as-agents.md).
- [Learn how to handle requests and responses](./request-and-response.md) in workflows.
- [Learn how to manage state](./shared-states.md) in workflows.
- [Learn how to create checkpoints and resume from them](./checkpointing.md).
