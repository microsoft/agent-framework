// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Workflow;

/// <summary>
/// This class demonstrates the use of agents within a workflow.
/// </summary>
public class Step02_Agents_In_Workflow(ITestOutputHelper output) : WorkflowSample(output)
{
    [Fact]
    public async Task RunAsync()
    {
        // Create agents
        AIAgent frenchAgent = GetTranslationAgent("French");
        AIAgent spanishAgent = GetTranslationAgent("Spanish");
        AIAgent englishAgent = GetTranslationAgent("English");

        // Build the workflow
        WorkflowBuilder builder = new(frenchAgent);
        builder.AddEdge(frenchAgent, spanishAgent);
        builder.AddEdge(spanishAgent, englishAgent);
        var workflow = builder.Build<ChatMessage>();

        // Execute the workflow
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, new ChatMessage(ChatRole.User, "Hello World!"));
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));
        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is AgentRunUpdateEvent executorComplete)
            {
                Console.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
            }
        }
    }

    private ChatClientAgent GetTranslationAgent(string targetLanguage)
    {
        string instructions = $"You are a translation assistant that translates the provided text to {targetLanguage}.";
        return new ChatClientAgent(GetAzureOpenAIChatClient(), instructions);
    }
}
