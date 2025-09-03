// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Workflow;

/// <summary>
/// This sample shows how to use AI agents as executors within a workflow.
///
/// Instead of simple text processing executors, this workflow uses three translation agents:
/// 1. French Agent - translates input text to French
/// 2. Spanish Agent - translates French text to Spanish
/// 3. English Agent - translates Spanish text back to English
///
/// The agents are connected sequentially, creating a translation chain that demonstrates
/// how AI-powered components can be seamlessly integrated into workflow pipelines.
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

    /// <summary>
    /// Creates a translation agent for the specified target language.
    /// </summary>
    /// <param name="targetLanguage">The target language for translation</param>
    /// <returns>A ChatClientAgent configured for the specified language</returns>
    private ChatClientAgent GetTranslationAgent(string targetLanguage)
    {
        string instructions = $"You are a translation assistant that translates the provided text to {targetLanguage}.";
        return new ChatClientAgent(GetAzureOpenAIChatClient(), instructions);
    }
}
