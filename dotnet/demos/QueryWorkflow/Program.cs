// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using Microsoft.Shared.Diagnostics;

namespace Demo.DeclarativeWorkflow;

internal static class Program
{
    public static async Task Main(string[] args)
    {
        string workflowId = GetWorkflowId();

        // Load configuration and create kernel with Azure OpenAI Chat Completion service
        IConfiguration config = InitializeConfig();
        Dictionary<string, string> nameCache = [];
        string foundryProjectEndpoint = config["AzureAI:Endpoint"] ?? throw new InvalidOperationException("Undefined configuration: AzureAI:Endpoint");
        PersistentAgentsClient client = new(foundryProjectEndpoint, new AzureCliCredential());

        await foreach (PersistentThreadMessage message in client.Messages.GetMessagesAsync(workflowId, order: ListSortOrder.Ascending))
        {
            Task<Azure.Response<ThreadRun>>? runTask = null;
            if (message.RunId is not null)
            {
                runTask = client.Runs.GetRunAsync(workflowId, message.RunId);
            }
            try
            {
                string? agentName = $"{message.Role}";
                if (message.AssistantId is not null)
                {
                    if (!nameCache.TryGetValue(message.AssistantId, out agentName))
                    {
                        PersistentAgent agent = await client.Administration.GetAgentAsync(message.AssistantId);
                        nameCache[message.AssistantId] = agent.Name;
                        agentName = agent.Name;
                    }
                }
                Console.ForegroundColor = ConsoleColor.Cyan;
                Console.Write($"\n{agentName.ToUpperInvariant()}:");
                Console.ForegroundColor = ConsoleColor.DarkGray;
                Console.WriteLine($" [{message.Id}]");

                Console.ForegroundColor = message.Role == MessageRole.User ? ConsoleColor.White : ConsoleColor.Gray;
                Console.WriteLine(message.ContentItems.OfType<MessageTextContent>().FirstOrDefault()?.Text);
                Console.ForegroundColor = ConsoleColor.DarkGray;

                if (runTask is not null)
                {
                    ThreadRun messageRun = await runTask;
                    Console.WriteLine($"[Tokens Total: {messageRun.Usage.TotalTokens}, Input: {messageRun.Usage.PromptTokens}, Output: {messageRun.Usage.CompletionTokens}]");
                }
            }
            finally
            {
                Console.ResetColor();
            }
        }

        string GetWorkflowId()
        {
            string? workflowId = args.FirstOrDefault();
            if (string.IsNullOrWhiteSpace(workflowId))
            {
                workflowId = Console.ReadLine()?.Trim();
            }
            if (!string.IsNullOrWhiteSpace(workflowId))
            {
                try
                {
                    Console.ForegroundColor = ConsoleColor.Cyan;

                    Console.Write("\nWORKFLOW: ");

                    Console.ForegroundColor = ConsoleColor.Yellow;

                    if (!string.IsNullOrWhiteSpace(workflowId))
                    {
                        Console.WriteLine(workflowId);
                        return workflowId;
                    }

                    Console.WriteLine();

                    return workflowId.Trim();
                }
                finally
                {
                    Console.ResetColor();
                }
            }
            throw new ArgumentException("Workflow ID is required.");
        }
    }

    // Load configuration from user-secrets
    private static IConfigurationRoot InitializeConfig() =>
        new ConfigurationBuilder()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .Build();
}
