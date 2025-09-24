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
using Microsoft.Agents.Workflows.Declarative.Events;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;

namespace Demo.DeclarativeWorkflow;

/// <summary>
/// HOW TO: Create a workflow from a declarative (yaml based) definition.
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
        string? workflowFile = ParseWorkflowFile(args);
        if (workflowFile is null)
        {
            Notify("\nUsage: DeclarativeWorkflow <workflow-file> [<input>]\n");
            return;
        }

        string? workflowInput = ParseWorkflowInput(args);

        Program program = new(workflowFile, workflowInput);
        await program.ExecuteAsync();
    }

    private async Task ExecuteAsync()
    {
        // Read and parse the declarative workflow.
        Notify($"\nWORKFLOW: Parsing {Path.GetFullPath(this.WorkflowFile)}");

        Stopwatch timer = Stopwatch.StartNew();

        Workflow<string> workflow = this.CreateWorkflow();

        Notify($"\nWORKFLOW: Defined {timer.Elapsed}");

        Notify("\nWORKFLOW: Starting...");

        // Run the workflow, just like any other workflow
        string input = this.GetWorkflowInput();

        CheckpointManager checkpointManager = CheckpointManager.Default;
        Checkpointed<StreamingRun> run = await InProcessExecution.StreamAsync(workflow, input, checkpointManager);

        bool isComplete = false;
        InputResponse? response = null;
        do
        {
            ExternalRequest? inputRequest = await this.MonitorWorkflowRunAsync(run, response);
            if (inputRequest is not null)
            {
                Notify("\nWORKFLOW: Yield");

                if (this.LastCheckpoint is null)
                {
                    throw new InvalidOperationException("Checkpoint information missing after external request.");
                }

                // Process the external request.
                response = HandleExternalRequest(inputRequest);

                // Let's resume on an entirely new workflow instance to demonstrate checkpoint portability.
                workflow = this.CreateWorkflow();

                // Restore the latest checkpoint.
                Debug.WriteLine($"RESTORE #{this.LastCheckpoint.CheckpointId}");
                Notify("\nWORKFLOW: Restore");
                run = await InProcessExecution.ResumeStreamAsync(workflow, this.LastCheckpoint, checkpointManager);
            }
            else
            {
                isComplete = true;
            }
        }
        while (!isComplete);

        Notify("\nWORKFLOW: Done!\n");
    }

    private Workflow<string> CreateWorkflow()
    {
        // Use DeclarativeWorkflowBuilder to build a workflow based on a YAML file.
        DeclarativeWorkflowOptions options =
            new(new AzureAgentProvider(this.FoundryEndpoint, new AzureCliCredential()))
            {
                Configuration = this.Configuration
            };

        return DeclarativeWorkflowBuilder.Build<string>(this.WorkflowFile, options);
    }

    private const string ConfigKeyFoundryEndpoint = "FOUNDRY_PROJECT_ENDPOINT";

    private static Dictionary<string, string> NameCache { get; } = [];
    private static HashSet<string> FileCache { get; } = [];

    private string WorkflowFile { get; }
    private string? WorkflowInput { get; }
    private string FoundryEndpoint { get; }
    private PersistentAgentsClient FoundryClient { get; }
    private IConfiguration Configuration { get; }
    private CheckpointInfo? LastCheckpoint { get; set; }

    private Program(string workflowFile, string? workflowInput)
    {
        this.WorkflowFile = workflowFile;
        this.WorkflowInput = workflowInput;

        this.Configuration = InitializeConfig();

        this.FoundryEndpoint = this.Configuration[ConfigKeyFoundryEndpoint] ?? throw new InvalidOperationException($"Undefined configuration setting: {ConfigKeyFoundryEndpoint}");
        this.FoundryClient = new PersistentAgentsClient(this.FoundryEndpoint, new AzureCliCredential());
    }

    private async Task<ExternalRequest?> MonitorWorkflowRunAsync(Checkpointed<StreamingRun> run, InputResponse? response = null)
    {
        string? messageId = null;

        await foreach (WorkflowEvent workflowEvent in run.Run.WatchStreamAsync().ConfigureAwait(false))
        {
            switch (workflowEvent)
            {
                case ExecutorInvokedEvent executorInvoked:
                    Debug.WriteLine($"EXECUTOR ENTER #{executorInvoked.ExecutorId}");
                    break;

                case ExecutorCompletedEvent executorCompleted:
                    Debug.WriteLine($"EXECUTOR EXIT #{executorCompleted.ExecutorId}");
                    break;

                case DeclarativeActionInvokedEvent actionInvoked:
                    Debug.WriteLine($"ACTION ENTER #{actionInvoked.ActionId} [{actionInvoked.ActionType}]");
                    break;

                case DeclarativeActionCompletedEvent actionComplete:
                    Debug.WriteLine($"ACTION EXIT #{actionComplete.ActionId} [{actionComplete.ActionType}]");
                    break;

                case ExecutorFailedEvent executorFailure:
                    Debug.WriteLine($"STEP ERROR #{executorFailure.ExecutorId}: {executorFailure.Data?.Message ?? "Unknown"}");
                    break;

                case SuperStepCompletedEvent checkpointCompleted:
                    this.LastCheckpoint = checkpointCompleted.CompletionInfo?.Checkpoint;
                    Debug.WriteLine($"CHECKPOINT x{checkpointCompleted.StepNumber} [{this.LastCheckpoint?.CheckpointId ?? "(none)"}]");
                    break;

                case RequestInfoEvent requestInfo:
                    Debug.WriteLine($"REQUEST #{requestInfo.Request.RequestId}");
                    if (response is not null)
                    {
                        ExternalResponse requestResponse = requestInfo.Request.CreateResponse(response);
                        await run.Run.SendResponseAsync(requestResponse).ConfigureAwait(false);
                        response = null;
                    }
                    else
                    {
                        return requestInfo.Request;
                    }
                    break;

                case ConversationUpdateEvent invokeEvent:
                    Debug.WriteLine($"CONVERSATION: {invokeEvent.Data}");
                    break;

                case MessageActivityEvent activityEvent:
                    Console.ForegroundColor = ConsoleColor.Cyan;
                    Console.WriteLine("\nACTIVITY:");
                    Console.ForegroundColor = ConsoleColor.Yellow;
                    Console.WriteLine(activityEvent.Message.Trim());
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
                                if (!NameCache.TryGetValue(agentId, out string? realName))
                                {
                                    PersistentAgent agent = await this.FoundryClient.Administration.GetAgentAsync(agentId);
                                    NameCache[agentId] = agent.Name;
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
                            if (fileId is not null && FileCache.Add(fileId))
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
                        if (messageEvent.Response.Usage is not null)
                        {
                            Console.ForegroundColor = ConsoleColor.DarkGray;
                            Console.WriteLine($"[Tokens Total: {messageEvent.Response.Usage.TotalTokenCount}, Input: {messageEvent.Response.Usage.InputTokenCount}, Output: {messageEvent.Response.Usage.OutputTokenCount}]");
                        }
                    }
                    finally
                    {
                        Console.ResetColor();
                    }
                    break;
            }
        }

        return default;
    }
    private static InputResponse HandleExternalRequest(ExternalRequest request)
    {
        InputRequest? message = request.Data.As<InputRequest>();
        string? userInput;
        do
        {
            Console.ForegroundColor = ConsoleColor.DarkGreen;
            Console.Write($"\n{message?.Prompt ?? "INPUT:"} ");
            Console.ForegroundColor = ConsoleColor.White;
            userInput = Console.ReadLine();
        }
        while (string.IsNullOrWhiteSpace(userInput));

        return new InputResponse(userInput);
    }

    private static string? ParseWorkflowFile(string[] args)
    {
        string? workflowFile = args.FirstOrDefault();
        if (string.IsNullOrWhiteSpace(workflowFile))
        {
            return null;
        }

        if (!File.Exists(workflowFile) && !Path.IsPathFullyQualified(workflowFile))
        {
            string? repoFolder = GetRepoFolder();
            if (repoFolder is not null)
            {
                workflowFile = Path.Combine(repoFolder, "workflow-samples", workflowFile);
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
