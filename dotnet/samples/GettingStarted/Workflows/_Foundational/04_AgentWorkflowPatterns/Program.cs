// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace WorkflowAgentsInWorkflowsSample;

/// <summary>
/// This sample introduces the use of AI agents as executors within a workflow,
/// using <see cref="AgentWorkflowBuilder"/> to compose the agents into one of
/// several common patterns.
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - An Azure OpenAI chat completion deployment must be configured.
/// </remarks>
public static class Program
{
    private static async Task Main()
    {
        // Set up the Azure OpenAI client.
        var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
        var client = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential()).GetChatClient(deploymentName).AsIChatClient();

        Console.Write("Choose workflow type ('sequential', 'concurrent', 'handoffs', 'groupchat'): ");
        switch (Console.ReadLine())
        {
            case "sequential":
                await RunWorkflowAsync(
                    AgentWorkflowBuilder.BuildSequential(from lang in (string[])["French", "Spanish", "English"] select GetTranslationAgent(lang, client)),
                    [new(ChatRole.User, "Hello, world!")]);
                break;

            case "concurrent":
                await RunWorkflowAsync(
                    AgentWorkflowBuilder.BuildConcurrent(from lang in (string[])["French", "Spanish", "English"] select GetTranslationAgent(lang, client)),
                    [new(ChatRole.User, "Hello, world!")]);
                break;

            case "handoffs":
                ChatClientAgent historyTutor = new(client,
                    "You provide assistance with historical queries. Explain important events and context clearly. Only respond about history.",
                    "history_tutor",
                    "Specialist agent for historical questions");
                ChatClientAgent mathTutor = new(client,
                    "You provide help with math problems. Explain your reasoning at each step and include examples. Only respond about math.",
                    "math_tutor",
                    "Specialist agent for math questions");
                ChatClientAgent triageAgent = new(client,
                    "You determine which agent to use based on the user's homework question. ALWAYS handoff to another agent.",
                    "triage_agent",
                    "Routes messages to the appropriate specialist agent");
                var workflow = AgentWorkflowBuilder.CreateHandoffBuilderWith(triageAgent)
                    .WithHandoffs(triageAgent, [mathTutor, historyTutor])
                    .WithHandoffs([mathTutor, historyTutor], triageAgent)
                    .Build();

                List<ChatMessage> messages = [];
                while (true)
                {
                    Console.Write("Q: ");
                    messages.Add(new(ChatRole.User, Console.ReadLine()!));
                    messages.AddRange(await RunWorkflowAsync(workflow, messages));
                }

            case "groupchat":
                await RunWorkflowAsync(
                    AgentWorkflowBuilder.CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = 5 })
                        .AddParticipants(from lang in (string[])["French", "Spanish", "English"] select GetTranslationAgent(lang, client))
                        .Build(),
                    [new(ChatRole.User, "Hello, world!")]);
                break;

            default:
                throw new InvalidOperationException("Invalid workflow type.");
        }

        static async Task<List<ChatMessage>> RunWorkflowAsync(Workflow workflow, List<ChatMessage> messages)
        {
            string? lastExecutorId = null;

            await using StreamingRun run = await InProcessExecution.StreamAsync(workflow, messages);
            await run.TrySendMessageAsync(new TurnToken(emitEvents: true));
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                if (evt is AgentRunUpdateEvent e)
                {
                    if (e.ExecutorId != lastExecutorId)
                    {
                        lastExecutorId = e.ExecutorId;
                        Console.WriteLine();
                        Console.WriteLine(e.ExecutorId);
                    }

                    Console.Write(e.Update.Text);
                    if (e.Update.Contents.OfType<FunctionCallContent>().FirstOrDefault() is FunctionCallContent call)
                    {
                        Console.WriteLine();
                        Console.WriteLine($"  [Calling function '{call.Name}' with arguments: {JsonSerializer.Serialize(call.Arguments)}]");
                    }
                }
                else if (evt is WorkflowOutputEvent output)
                {
                    Console.WriteLine();
                    return output.As<List<ChatMessage>>()!;
                }
            }

            return [];
        }
    }

    /// <summary>Creates a translation agent for the specified target language.</summary>
    private static ChatClientAgent GetTranslationAgent(string targetLanguage, IChatClient chatClient) =>
        new(chatClient,
            $"You are a translation assistant who only responds in {targetLanguage}. Respond to any " +
            $"input by outputting the name of the input language and then translating the input to {targetLanguage}.");
}
