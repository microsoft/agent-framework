// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use the AG-UI client to connect to a remote AG-UI server
// and display streaming updates including RunStartedContent, TextContent, and RunFinishedContent.

using System.CommandLine;
using System.Reflection;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AGUI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;

namespace AGUIClient;

public static class Program
{
    public static async Task<int> Main(string[] args)
    {
        // Create root command with options
        RootCommand rootCommand = new("AGUIClient");
        rootCommand.SetAction((_, ct) => HandleCommandsAsync(ct));

        // Run the command
        return await rootCommand.Parse(args).InvokeAsync();
    }

    private static async Task HandleCommandsAsync(CancellationToken cancellationToken)
    {
        // Set up the logging
        using ILoggerFactory loggerFactory = LoggerFactory.Create(builder =>
        {
            builder.AddConsole();
            builder.SetMinimumLevel(LogLevel.Information);
        });
        ILogger logger = loggerFactory.CreateLogger("AGUIClient");

        // Retrieve configuration settings
        IConfigurationRoot configRoot = new ConfigurationBuilder()
            .AddEnvironmentVariables()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .Build();

        string serverUrl = configRoot["AGUI_SERVER_URL"] ?? "http://localhost:5100";

        logger.LogInformation("Connecting to AG-UI server at: {ServerUrl}", serverUrl);

        // Create the AG-UI client agent
        HttpClient httpClient = new()
        {
            Timeout = TimeSpan.FromSeconds(60)
        };

        // Initial system message with instructions
        List<ChatMessage> initialMessages = [new(ChatRole.System, "You are a helpful assistant.")];

        AGUIAgent agent = new(
            id: "agui-client",
            description: "AG-UI Client Agent",
            messages: initialMessages,
            httpClient: httpClient,
            endpoint: serverUrl);

        AgentThread thread = agent.GetNewThread();

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

                // Create chat messages with system message and user message
                List<ChatMessage> messages =
                [
                    new(ChatRole.System, "You are a helpful assistant."),
                    new(ChatRole.User, message)
                ];

                // Call RunStreamingAsync to get streaming updates
                await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(messages, thread, cancellationToken: cancellationToken))
                {
                    // Display different content types with appropriate formatting
                    foreach (AIContent content in update.Contents)
                    {
                        switch (content)
                        {
                            case RunStartedContent runStarted:
                                Console.ForegroundColor = ConsoleColor.Yellow;
                                Console.WriteLine($"\n[Run Started - Thread: {runStarted.ThreadId}, Run: {runStarted.RunId}]");
                                Console.ResetColor();
                                break;

                            case TextContent textContent:
                                Console.ForegroundColor = ConsoleColor.Cyan;
                                Console.Write(textContent.Text);
                                Console.ResetColor();
                                break;

                            case RunFinishedContent runFinished:
                                Console.ForegroundColor = ConsoleColor.Green;
                                Console.WriteLine($"\n[Run Finished - Thread: {runFinished.ThreadId}, Run: {runFinished.RunId}]");
                                Console.ResetColor();
                                break;

                            case RunErrorContent runError:
                                Console.ForegroundColor = ConsoleColor.Red;
                                Console.WriteLine($"\n[Run Error - Code: {runError.Code}, Message: {runError.Message}]");
                                Console.ResetColor();
                                break;
                        }
                    }
                }

                Console.WriteLine();
            }
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "An error occurred while running the AGUIClient");
            return;
        }
    }
}
