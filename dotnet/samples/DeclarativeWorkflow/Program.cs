// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Declarative;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;

namespace Demo.DeclarativeWorkflow;

/// <summary>
/// HOW TO: Create a workflow from a declartive (yaml based) definition.
/// </summary>
/// <remarks>
/// <b>Configuration</b>
/// Define FOUNDRY_PROJECT_ENDPOINT as a user-secret or environment variable that
/// points to your Foundry project endpoint.
/// <b>Usage</b>
/// Provide the path to the workflow definition file as the first argument.
/// All other arguments are intepreted as a queue of inputs.
/// When no input is queued, interactive input is requested from the console.
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
        // Read and parse the declarative workflow.
        Notify($"WORKFLOW: Parsing {Path.GetFullPath(this.WorkflowFile)}");

        Stopwatch timer = Stopwatch.StartNew();

        // Use DeclarativeWorkflowBuilder to build a workflow based on a YAML file.
        DeclarativeWorkflowOptions options =
            new(new FoundryAgentProvider(this.FoundryEndpoint, new AzureCliCredential()))
            {
                Configuration = this.Configuration
            };
        Workflow<string> workflow = DeclarativeWorkflowBuilder.Build<string>(this.WorkflowFile, options);

        Notify($"\nWORKFLOW: Defined {timer.Elapsed}");

        Notify("\nWORKFLOW: Starting...");

        // Run the workflow, just like any other workflow
        string input = this.GetWorkflowInput();
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, input);
        await this.MonitorWorkflowRunAsync(run);

        Notify("\nWORKFLOW: Done!");
    }

    private const string DefaultWorkflow = "HelloWorld.yaml";
    private const string ConfigKeyFoundryEndpoint = "FOUNDRY_PROJECT_ENDPOINT";

    private static readonly Dictionary<string, string> s_nameCache = [];
    private static readonly HashSet<string> s_fileCache = [];

    private string WorkflowFile { get; }
    private string? WorkflowInput { get; }
    private string FoundryEndpoint { get; }
    private PersistentAgentsClient FoundryClient { get; }
    private IConfiguration Configuration { get; }

    private Program(string[] args)
    {
        this.WorkflowFile = ParseWorkflowFile(args);
        this.WorkflowInput = ParseWorkflowInput(args);

        this.Configuration = InitializeConfig();

        this.FoundryEndpoint = this.Configuration[ConfigKeyFoundryEndpoint] ?? throw new InvalidOperationException($"Undefined configuration setting: {ConfigKeyFoundryEndpoint}");
        this.FoundryClient = new PersistentAgentsClient(this.FoundryEndpoint, new AzureCliCredential());
    }

    private async Task MonitorWorkflowRunAsync(StreamingRun run)
    {
        string? messageId = null;

        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is ExecutorInvokeEvent executorInvoked)
            {
                Debug.WriteLine($"STEP ENTER #{executorInvoked.ExecutorId}");
            }
            else if (evt is ExecutorCompleteEvent executorComplete)
            {
                Debug.WriteLine($"STEP EXIT #{executorComplete.ExecutorId}");
            }
            else if (evt is ExecutorFailureEvent executorFailure)
            {
                Debug.WriteLine($"STEP ERROR #{executorFailure.ExecutorId}: {executorFailure.Data?.Message ?? "Unknown"}");
            }
            else if (evt is ConversationUpdateEvent invokeEvent)
            {
                Debug.WriteLine($"CONVERSATION: {invokeEvent.Data}");
            }
            else if (evt is AgentRunUpdateEvent streamEvent)
            {
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
            }
            else if (evt is AgentRunResponseEvent messageEvent)
            {
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
            }
        }
    }

    private static string ParseWorkflowFile(string[] args)
    {
        string workflowFile = args.FirstOrDefault() ?? DefaultWorkflow;

        if (!File.Exists(workflowFile) && !Path.IsPathFullyQualified(workflowFile))
        {
            string? repoFolder = GetRepoFolder();
            if (repoFolder is not null)
            {
                workflowFile = Path.Combine(repoFolder, "Workflows", workflowFile);
                workflowFile = Path.ChangeExtension(workflowFile, ".yaml");
            }
        }

        if (!File.Exists(workflowFile))
        {
            throw new InvalidOperationException($"Unable to locate workflow: {Path.GetFullPath(workflowFile)}.");
        }

        return workflowFile;

        static string? GetRepoFolder()
        {
            DirectoryInfo? current = new(Directory.GetCurrentDirectory());

            while (current is not null)
            {
                if (Directory.Exists(Path.Combine(current.FullName, ".git")))
                {
                    return current.FullName;
                }

                current = current.Parent;
            }

            return null;
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
        if (args.Length == 0)
        {
            return null;
        }

        string[] workflowInput = [.. args.Skip(1)];

        return workflowInput.FirstOrDefault();
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
