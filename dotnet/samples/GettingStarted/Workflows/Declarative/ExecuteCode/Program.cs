// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Reflection;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Declarative;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Test.WorkflowProviders;

namespace Demo.DeclarativeCode;

/// <summary>
/// HOW TO: Execute a declarative workflow that has been converted to code.
/// </summary>
/// <remarks>
/// <b>Configuration</b>
/// Define FOUNDRY_PROJECT_ENDPOINT as a user-secret or environment variable that
/// points to your Foundry project endpoint.
/// </remarks>
internal sealed class Program
{
    public static async Task Main(string[] args)
    {
        Program program = new(args);
        await program.ExecuteAsync();
    }

    private async Task ExecuteAsync()
    {
        // Use DeclarativeWorkflowBuilder to build a workflow based on a YAML file.
        DeclarativeWorkflowOptions options =
            new(new AzureAgentProvider(this.FoundryEndpoint, new AzureCliCredential()))
            {
                Configuration = this.Configuration
            };

        // Use the generated provider to create a workflow instance.
        Workflow workflow = TestWorkflowProvider.CreateWorkflow<string>(options);

        Notify("\nWORKFLOW: Starting...");

        // Run the workflow, just like any other workflow
        string input = this.GetWorkflowInput();
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, input);
        await this.MonitorAndDisposeWorkflowRunAsync(run);

        Notify("\nWORKFLOW: Done!");
    }

    private const string ConfigKeyFoundryEndpoint = "FOUNDRY_PROJECT_ENDPOINT";

    private static readonly Dictionary<string, string> s_nameCache = [];
    private static readonly HashSet<string> s_fileCache = [];

    private string? WorkflowInput { get; }
    private string FoundryEndpoint { get; }
    private PersistentAgentsClient FoundryClient { get; }
    private IConfiguration Configuration { get; }

    private Program(string[] args)
    {
        this.WorkflowInput = ParseWorkflowInput(args);

        this.Configuration = InitializeConfig();

        this.FoundryEndpoint = this.Configuration[ConfigKeyFoundryEndpoint] ?? throw new InvalidOperationException($"Undefined configuration setting: {ConfigKeyFoundryEndpoint}");
        this.FoundryClient = new PersistentAgentsClient(this.FoundryEndpoint, new AzureCliCredential());
    }

    private async Task MonitorAndDisposeWorkflowRunAsync(StreamingRun run)
    {
        await using IAsyncDisposable disposeRun = run;

        string? messageId = null;

        await foreach (WorkflowEvent workflowEvent in run.WatchStreamAsync())
        {
            switch (workflowEvent)
            {
                case ExecutorInvokedEvent executorInvoked:
                    Debug.WriteLine($"STEP ENTER #{executorInvoked.ExecutorId}");
                    break;

                case ExecutorCompletedEvent executorComplete:
                    Debug.WriteLine($"STEP EXIT #{executorComplete.ExecutorId}");
                    break;

                case ExecutorFailedEvent executorFailure:
                    Debug.WriteLine($"STEP ERROR #{executorFailure.ExecutorId}: {executorFailure.Data?.Message ?? "Unknown"}");
                    break;

                case WorkflowErrorEvent workflowError:
                    throw workflowError.Data as Exception ?? new InvalidOperationException("Unexpected failure...");

                case ConversationUpdateEvent invokeEvent:
                    Debug.WriteLine($"CONVERSATION: {invokeEvent.Data}");
                    break;

                case AgentRunUpdateEvent streamEvent:
                    if (!string.Equals(messageId, streamEvent.Update.MessageId, StringComparison.Ordinal))
                    {
                        messageId = streamEvent.Update.MessageId;

                        if (messageId is not null)
                        {
                            string? agentId = streamEvent.Update.AuthorName;
                            if (agentId is not null)
                            {
                                if (!s_nameCache.TryGetValue(agentId, out string? realName))
                                {
                                    PersistentAgent agent = await this.FoundryClient.Administration.GetAgentAsync(agentId);
                                    s_nameCache[agentId] = agent.Name;
                                    realName = agent.Name;
                                }
                                agentId = realName;
                            }
                            agentId ??= nameof(ChatRole.Assistant);
                            Console.ForegroundColor = ConsoleColor.Cyan;
                            Console.Write($"\n{agentId.ToUpperInvariant()}:");
                            Console.ForegroundColor = ConsoleColor.DarkGray;
                            Console.WriteLine($" [{messageId}]");
                        }
                    }

                    ChatResponseUpdate? chatUpdate = streamEvent.Update.RawRepresentation as ChatResponseUpdate;
                    switch (chatUpdate?.RawRepresentation)
                    {
                        case MessageContentUpdate messageUpdate:
                            string? fileId = messageUpdate.ImageFileId ?? messageUpdate.TextAnnotation?.OutputFileId;
                            if (fileId is not null && s_fileCache.Add(fileId))
                            {
                                BinaryData content = await this.FoundryClient.Files.GetFileContentAsync(fileId);
                                await DownloadFileContentAsync(Path.GetFileName(messageUpdate.TextAnnotation?.TextToReplace ?? "response.png"), content);
                            }
                            break;
                    }
                    try
                    {
                        Console.ResetColor();
                        Console.Write(streamEvent.Data);
                    }
                    finally
                    {
                        Console.ResetColor();
                    }
                    break;

                case AgentRunResponseEvent messageEvent:
                    try
                    {
                        Console.WriteLine();
                        if (messageEvent.Response.AgentId is null)
                        {
                            Console.ForegroundColor = ConsoleColor.Cyan;
                            Console.WriteLine("ACTIVITY:");
                            Console.ForegroundColor = ConsoleColor.Yellow;
                            Console.WriteLine(messageEvent.Response?.Text.Trim());
                        }
                        else
                        {
                            if (messageEvent.Response.Usage is not null)
                            {
                                Console.ForegroundColor = ConsoleColor.DarkGray;
                                Console.WriteLine($"[Tokens Total: {messageEvent.Response.Usage.TotalTokenCount}, Input: {messageEvent.Response.Usage.InputTokenCount}, Output: {messageEvent.Response.Usage.OutputTokenCount}]");
                            }
                        }
                    }
                    finally
                    {
                        Console.ResetColor();
                    }
                    break;
            }
        }
    }

    private string GetWorkflowInput()
    {
        string? input = this.WorkflowInput;

        try
        {
            Console.ForegroundColor = ConsoleColor.DarkGreen;

            Console.Write("\nINPUT: ");

            Console.ForegroundColor = ConsoleColor.White;

            if (!string.IsNullOrWhiteSpace(input))
            {
                Console.WriteLine(input);
                return input;
            }
            while (string.IsNullOrWhiteSpace(input))
            {
                input = Console.ReadLine();
            }

            return input.Trim();
        }
        finally
        {
            Console.ResetColor();
        }
    }

    private static string? ParseWorkflowInput(string[] args)
    {
        return args?.FirstOrDefault();
    }

    // Load configuration from user-secrets
    private static IConfigurationRoot InitializeConfig() =>
        new ConfigurationBuilder()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .AddEnvironmentVariables()
            .Build();

    private static void Notify(string message)
    {
        Console.ForegroundColor = ConsoleColor.Cyan;
        try
        {
            Console.WriteLine(message);
        }
        finally
        {
            Console.ResetColor();
        }
    }

    private static async ValueTask DownloadFileContentAsync(string filename, BinaryData content)
    {
        string filePath = Path.Combine(Path.GetTempPath(), Path.GetFileName(filename));
        filePath = Path.ChangeExtension(filePath, ".png");

        await File.WriteAllBytesAsync(filePath, content.ToArray());

        Process.Start(
            new ProcessStartInfo
            {
                FileName = "cmd.exe",
                Arguments = $"/C start {filePath}"
            });
    }
}
