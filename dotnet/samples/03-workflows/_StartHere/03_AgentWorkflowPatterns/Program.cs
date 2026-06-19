// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Azure.AI.Projects;
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
/// - An Azure AI Foundry project endpoint and model must be configured.
/// </remarks>
public static class Program
{
    private static async Task Main()
    {
        // Set up the Azure AI Foundry client.
        var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
        var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";
        AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

        Console.Write("Choose workflow type ('sequential', 'sequential-chain-only', 'concurrent', 'handoffs', 'groupchat'): ");
        switch (Console.ReadLine())
        {
            case "sequential":
                await RunWorkflowAsync(
                    AgentWorkflowBuilder.BuildSequential(from lang in (string[])["French", "Spanish", "English"] select GetTranslationAgent(lang, aiProjectClient, deploymentName)),
                    [new(ChatRole.User, "Hello, world!")]);
                break;

            case "sequential-chain-only":
                await RunWorkflowAsync(
                    AgentWorkflowBuilder.BuildSequential(
                        chainOnlyAgentResponses: true,
                        from lang in (string[])["French", "Spanish", "English"] select GetTranslationAgent(lang, aiProjectClient, deploymentName)),
                    [new(ChatRole.User, "Hello, world!")]);
                break;

            case "concurrent":
                await RunWorkflowAsync(
                    AgentWorkflowBuilder.BuildConcurrent(from lang in (string[])["French", "Spanish", "English"] select GetTranslationAgent(lang, aiProjectClient, deploymentName)),
                    [new(ChatRole.User, "Hello, world!")]);
                break;

            case "handoffs":
                ChatClientAgent historyTutor = aiProjectClient.AsAIAgent(
                    model: deploymentName,
                    instructions: "You provide assistance with historical queries. Explain important events and context clearly. Only respond about history.",
                    name: "history_tutor",
                    description: "Specialist agent for historical questions");
                ChatClientAgent mathTutor = aiProjectClient.AsAIAgent(
                    model: deploymentName,
                    instructions: "You provide help with math problems. Explain your reasoning at each step and include examples. Only respond about math.",
                    name: "math_tutor",
                    description: "Specialist agent for math questions");
                ChatClientAgent triageAgent = aiProjectClient.AsAIAgent(
                    model: deploymentName,
                    instructions: "You determine which agent to use based on the user's homework question. ALWAYS handoff to another agent.",
                    name: "triage_agent",
                    description: "Routes messages to the appropriate specialist agent");
                var workflow = AgentWorkflowBuilder.CreateHandoffBuilderWith(triageAgent)
                    .WithHandoffs(triageAgent, [mathTutor, historyTutor])
                    .WithHandoffs([mathTutor, historyTutor], triageAgent)
                    .Build();

                List<ChatMessage> messages = [];
                while (true)
                {
                    Console.Write("Q: ");
                    messages.Add(new(ChatRole.User, Console.ReadLine()));
                    messages.AddRange(await RunWorkflowAsync(workflow, messages));
                }

            case "groupchat":
                await RunWorkflowAsync(
                    AgentWorkflowBuilder.CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = 5 })
                        .AddParticipants(from lang in (string[])["French", "Spanish", "English"] select GetTranslationAgent(lang, aiProjectClient, deploymentName))
                        .WithName("Translation Round Robin Workflow")
                        .WithDescription("A workflow where three translation agents take turns responding in a round-robin fashion.")
                        .Build(),
                    [new(ChatRole.User, "Hello, world!")]);
                break;

            default:
                throw new InvalidOperationException("Invalid workflow type.");
        }

        static async Task<List<ChatMessage>> RunWorkflowAsync(Workflow workflow, List<ChatMessage> messages)
        {
            string? lastExecutorId = null;

            await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, messages);
            await run.TrySendMessageAsync(new TurnToken(emitEvents: true));
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                if (evt is AgentResponseUpdateEvent e)
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
                else if (evt is WorkflowErrorEvent workflowError)
                {
                    Console.ForegroundColor = ConsoleColor.Red;
                    Console.Error.WriteLine(workflowError.Exception?.ToString() ?? "Unknown workflow error occurred.");
                    Console.ResetColor();
                }
                else if (evt is ExecutorFailedEvent executorFailed)
                {
                    Console.ForegroundColor = ConsoleColor.Red;
                    Console.Error.WriteLine($"Executor '{executorFailed.ExecutorId}' failed with {(executorFailed.Data == null ? "unknown error" : $"exception {executorFailed.Data}")}.");
                    Console.ResetColor();
                }
            }

            return [];
        }
    }

    /// <summary>Creates a translation agent for the specified target language.</summary>
    private static ChatClientAgent GetTranslationAgent(string targetLanguage, AIProjectClient client, string model) =>
        client.AsAIAgent(
            model: model,
            instructions: $"You are a translation assistant who only responds in {targetLanguage}. Respond to any " +
            $"input by outputting the name of the input language and then translating the input to {targetLanguage}.");
}
