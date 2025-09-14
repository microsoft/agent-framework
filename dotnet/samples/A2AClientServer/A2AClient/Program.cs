// Copyright (c) Microsoft. All rights reserved.

using System.CommandLine;
using System.CommandLine.Invocation;
using System.Reflection;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;

namespace A2A;

public static class Program
{
    public static async Task<int> Main(string[] args)
    {
        // Create root command with options
        var rootCommand = new RootCommand("A2AClient");
        rootCommand.SetHandler(HandleCommandsAsync);

        // Run the command
        return await rootCommand.InvokeAsync(args);
    }

    public static async Task HandleCommandsAsync(InvocationContext context)
    {
        // Set up the logging
        using var loggerFactory = LoggerFactory.Create(builder =>
        {
            builder.AddConsole();
            builder.SetMinimumLevel(LogLevel.Information);
        });
        var logger = loggerFactory.CreateLogger("A2AClient");

        // Retrieve configuration settings
        IConfigurationRoot configRoot = new ConfigurationBuilder()
            .AddEnvironmentVariables()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .Build();
        var apiKey = configRoot["A2AClient:ApiKey"] ?? throw new ArgumentException("A2AClient:ApiKey must be provided");
        var modelId = configRoot["A2AClient:ModelId"] ?? "gpt-4.1";
        var agentUrls = configRoot["A2AClient:AgentUrls"] ?? "http://localhost:5000/;http://localhost:5001/;http://localhost:5002/";

        // Create the Host agent
        var hostAgent = new HostClientAgent(loggerFactory);
        await hostAgent.InitializeAgentAsync(modelId, apiKey, agentUrls!.Split(";"));
        AgentThread thread = hostAgent.Agent!.GetNewThread();
        try
        {
            while (true)
            {
                // Get user message
                Console.Write("\nUser (:q or quit to exit): ");
                string? message = Console.ReadLine();
                if (string.IsNullOrWhiteSpace(message))
                {
                    Console.WriteLine("Request cannot be empty.");
                    continue;
                }

                if (message is ":q" or "quit")
                {
                    break;
                }

                var agentResponse = await hostAgent.Agent!.RunAsync(message, thread);
                foreach (var chatMessage in agentResponse.Messages)
                {
                    Console.ForegroundColor = ConsoleColor.Cyan;
                    Console.WriteLine($"\nAgent: {chatMessage.Text}");
                    Console.ResetColor();
                }
            }
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "An error occurred while running the A2AClient");
            return;
        }
    }
}
