// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use the AG-UI client to connect to a remote AG-UI server
// and display streaming updates including conversation/response metadata, text content, and errors.

using System.CommandLine;
using System.ComponentModel;
using System.Reflection;
using System.Text;
using AGUI.Abstractions;
using AGUI.Client;
using Microsoft.Agents.AI;
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
        using HttpClient httpClient = new()
        {
            Timeout = TimeSpan.FromSeconds(60)
        };

        var changeBackground = AIFunctionFactory.Create(
            () =>
            {
                Console.ForegroundColor = ConsoleColor.DarkBlue;
                Console.WriteLine("Changing color to blue");
            },
            name: "change_background_color",
            description: "Change the console background color to dark blue."
        );

        var readClientClimateSensors = AIFunctionFactory.Create(
            ([Description("The sensors measurements to include in the response")] SensorRequest request) =>
            {
                return new SensorResponse()
                {
                    Temperature = 22.5,
                    Humidity = 45.0,
                    AirQualityIndex = 75
                };
            },
            name: "read_client_climate_sensors",
            description: "Reads the climate sensor data from the client device.",
            serializerOptions: AGUIClientSerializerContext.Default.Options
        );

        var chatClient = new AGUIChatClient(new(httpClient, serverUrl)
        {
            JsonSerializerOptions = AGUIClientSerializerContext.Default.Options,
        });

        AIAgent agent = chatClient.AsAIAgent(
            name: "agui-client",
            description: "AG-UI Client Agent",
            tools: [changeBackground, readClientClimateSensors]);

        AgentSession session = await agent.CreateSessionAsync(cancellationToken);
        List<ChatMessage> messages = [new(ChatRole.System, "You are a helpful assistant.")];

        // AGUIChatClient is stateless: it never surfaces a ConversationId. AG-UI continuation is expressed
        // on the wire as the same threadId plus a parentRunId equal to the previous turn's runId. We read
        // both from each turn's RUN_STARTED event and send them back on the next turn via
        // ChatOptions.RawRepresentationFactory (the pattern the AG-UI samples use).
        string? threadId = null;
        string? previousRunId = null;
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

                messages.Add(new(ChatRole.User, message));

                // On continuation turns, carry the thread and the previous run id back to the stateless
                // client so the server resumes the same AG-UI conversation.
                AgentRunOptions? runOptions = previousRunId is null
                    ? null
                    : new ChatClientAgentRunOptions
                    {
                        ChatOptions = new ChatOptions
                        {
                            RawRepresentationFactory = _ => new RunAgentInput
                            {
                                ThreadId = threadId ?? string.Empty,
                                ParentRunId = previousRunId,
                            },
                        },
                    };

                // Call RunStreamingAsync to get streaming updates
                bool isFirstUpdate = true;
                string? currentRunId = null;
                var updates = new List<ChatResponseUpdate>();
                await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(messages, session, runOptions, cancellationToken))
                {
                    // Use AsChatResponseUpdate to access ChatResponseUpdate properties
                    ChatResponseUpdate chatUpdate = update.AsChatResponseUpdate();
                    updates.Add(chatUpdate);
                    // AGUIChatClient is stateless and never surfaces a ConversationId; the thread
                    // id and run id are carried on the AG-UI RUN_STARTED event's raw representation.
                    if (chatUpdate.RawRepresentation is RunStartedEvent runStarted)
                    {
                        threadId = runStarted.ThreadId;
                        currentRunId = runStarted.RunId;
                    }

                    // Display run started information from the first update
                    if (isFirstUpdate && threadId != null && update.ResponseId != null)
                    {
                        Console.ForegroundColor = ConsoleColor.Yellow;
                        Console.WriteLine($"\n[Run Started - Thread: {threadId}, Run: {update.ResponseId}]");
                        Console.ResetColor();
                        isFirstUpdate = false;
                    }

                    // Display different content types with appropriate formatting
                    foreach (AIContent content in update.Contents)
                    {
                        switch (content)
                        {
                            case TextContent textContent:
                                Console.ForegroundColor = ConsoleColor.Cyan;
                                Console.Write(textContent.Text);
                                Console.ResetColor();
                                break;

                            case FunctionCallContent functionCallContent:
                                Console.ForegroundColor = ConsoleColor.Green;
                                Console.WriteLine($"\n[Function Call - Name: {functionCallContent.Name}, Arguments: {PrintArguments(functionCallContent.Arguments)}]");
                                Console.ResetColor();
                                break;

                            case FunctionResultContent functionResultContent:
                                Console.ForegroundColor = ConsoleColor.Magenta;
                                if (functionResultContent.Exception != null)
                                {
                                    Console.WriteLine($"\n[Function Result - Exception: {functionResultContent.Exception}]");
                                }
                                else
                                {
                                    Console.WriteLine($"\n[Function Result - Result: {functionResultContent.Result}]");
                                }
                                Console.ResetColor();
                                break;

                            case ErrorContent errorContent:
                                Console.ForegroundColor = ConsoleColor.Red;
                                string code = errorContent.AdditionalProperties?["Code"] as string ?? "Unknown";
                                Console.WriteLine($"\n[Error - Code: {code}, Message: {errorContent.Message}]");
                                Console.ResetColor();
                                break;
                        }
                    }
                }
                if (updates.Count > 0 && !updates[^1].Contents.Any(c => c is TextContent))
                {
                    var lastUpdate = updates[^1];
                    Console.ForegroundColor = ConsoleColor.Yellow;
                    Console.WriteLine();
                    Console.WriteLine($"[Run Ended - Thread: {threadId}, Run: {lastUpdate.ResponseId}]");
                    Console.ResetColor();
                }
                // Remember this run as the parent of the next turn, and drop the local message buffer:
                // continuation now travels on the wire as threadId + parentRunId, so each turn sends only
                // the new user message.
                previousRunId = currentRunId;
                messages.Clear();
                Console.WriteLine();
            }
        }
        catch (OperationCanceledException)
        {
            logger.LogInformation("AGUIClient operation was canceled.");
        }
        catch (Exception ex) when (ex is not OutOfMemoryException and not StackOverflowException and not ThreadAbortException and not AccessViolationException)
        {
            logger.LogError(ex, "An error occurred while running the AGUIClient");
            return;
        }
    }

    private static string PrintArguments(IDictionary<string, object?>? arguments)
    {
        if (arguments == null)
        {
            return "";
        }
        var builder = new StringBuilder().AppendLine();
        foreach (var kvp in arguments)
        {
            builder
                .AppendLine($"   Name: {kvp.Key}")
                .AppendLine($"   Value: {kvp.Value}");
        }
        return builder.ToString();
    }
}
