// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.Workflows;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace WorkflowAsAnAgentsSample;

/// <summary>
/// This sample introduces the concepts workflows as agents, where a workflow can be
/// treated as an <see cref="AIAgent"/>. This allows you to interact with a workflow
/// as if it were a single agent.
///
/// In this example, we create a workflow that uses two language agents to process
/// input concurrently, one that responds in French and another that responds in English.
///
/// You will interact with the workflow in an interactive loop, sending messages and receiving
/// streaming responses from the workflow as if it were an agent who responds in both languages.
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - Foundational samples should be completed first.
/// - This sample uses concurrent processing.
/// - An Azure OpenAI endpoint and deployment name.
/// </remarks>
public static class Program
{
    private static async Task Main()
    {
        // Set up the Azure OpenAI client
        var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
        var chatClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential()).GetChatClient(deploymentName).AsIChatClient();

        // Create the workflow and turn it into an agent
        var workflow = WorkflowHelper.GetWorkflow(chatClient);
        var agent = workflow.AsAgent("workflow-agent", "Workflow Agent");
        var thread = agent.GetNewThread();

        // Start an interactive loop to interact with the workflow as if it were an agent
        while (true)
        {
            Console.WriteLine();
            Console.Write("User (or 'exit' to quit): ");
            string? input = Console.ReadLine();
            if (string.IsNullOrWhiteSpace(input) || input.Equals("exit", StringComparison.OrdinalIgnoreCase))
            {
                break;
            }

            await ProcessInputAsync(agent, thread, input);
        }

        // Helper method to process user input and display streaming responses. To display
        // multiple interleaved responses correctly, we buffer updates by message ID and
        // re-render all messages on each update.
        static async Task ProcessInputAsync(AIAgent agent, AgentThread thread, string input)
        {
            Dictionary<string, List<AgentRunResponseUpdate>> buffer = [];
            await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(input, thread).ConfigureAwait(false))
            {
                if (update.MessageId is null)
                {
                    // skip updates that don't have a message ID
                    continue;
                }
                Console.Clear();

                if (!buffer.TryGetValue(update.MessageId, out List<AgentRunResponseUpdate>? value))
                {
                    value = [];
                    buffer[update.MessageId] = value;
                }
                value.Add(update);

                foreach (var (messageId, segments) in buffer)
                {
                    string combinedText = string.Concat(segments);
                    Console.WriteLine($"{segments[0].AuthorName}: {combinedText}");
                    Console.WriteLine();
                }
            }
        }
    }
}
