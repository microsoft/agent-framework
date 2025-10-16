// Copyright (c) Microsoft. All rights reserved.

// Uncomment this to enable JSON checkpointing to the local file system.
//#define CHECKPOINT_JSON

using System.Diagnostics;
using System.Reflection;
using System.Text.Json;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows;
#if CHECKPOINT_JSON
using Microsoft.Agents.AI.Workflows.Checkpointing;
#endif
using Microsoft.Agents.AI.Workflows.Declarative;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
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

        Workflow workflow = this.CreateWorkflow();

        Notify($"\nWORKFLOW: Defined {timer.Elapsed}");

        Notify("\nWORKFLOW: Starting...");

        // Run the workflow, just like any other workflow
        string input = this.GetWorkflowInput();

#if CHECKPOINT_JSON
        // Use a file-system based JSON checkpoint store to persist checkpoints to disk.
        DirectoryInfo checkpointFolder = Directory.CreateDirectory(Path.Combine(".", $"chk-{DateTime.Now:yyMMdd-hhmmss-ff}"));
        CheckpointManager checkpointManager = CheckpointManager.CreateJson(new FileSystemJsonCheckpointStore(checkpointFolder));
#else
        // Use an in-memory checkpoint store that will not persist checkpoints beyond the lifetime of the process.
        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
#endif

        Checkpointed<StreamingRun> run = await InProcessExecution.StreamAsync(workflow, input, checkpointManager);

        bool isComplete = false;
        object? response = null;
        do
        {
            ExternalRequest? externalRequest = await this.MonitorAndDisposeWorkflowRunAsync(run, response);
            if (externalRequest is not null)
            {
                Notify("\nWORKFLOW: Yield");

                if (this.LastCheckpoint is null)
                {
                    throw new InvalidOperationException("Checkpoint information missing after external request.");
                }

                // Process the external request.
                response = await this.HandleExternalRequestAsync(externalRequest);

                // Let's resume on an entirely new workflow instance to demonstrate checkpoint portability.
                workflow = this.CreateWorkflow();

                // Restore the latest checkpoint.
                Debug.WriteLine($"RESTORE #{this.LastCheckpoint.CheckpointId}");
                Notify("\nWORKFLOW: Restore");

                run = await InProcessExecution.ResumeStreamAsync(workflow, this.LastCheckpoint, checkpointManager, run.Run.RunId);
            }
            else
            {
                isComplete = true;
            }
        }
        while (!isComplete);

        Notify("\nWORKFLOW: Done!\n");
    }

    /// <summary>
    /// Create the workflow from the declarative YAML.  Includes definition of the
    /// <see cref="DeclarativeWorkflowOptions" /> and the associated <see cref="WorkflowAgentProvider"/>.
    /// </summary>
    /// <remarks>
    /// The value assigned to <see cref="IncludeFunctions" /> controls on whether the function
    /// tools (<see cref="AIFunction"/>) initialized in the constructor are included for auto-invocation.
    /// </remarks>
    private Workflow CreateWorkflow()
    {
        // Use DeclarativeWorkflowBuilder to build a workflow based on a YAML file.
        AzureAgentProvider agentProvider = new(this.FoundryEndpoint, new AzureCliCredential())
        {
            // Functions included here will be auto-executed by the framework.
            Functions = IncludeFunctions ? this.FunctionMap.Values : null,
        };

        DeclarativeWorkflowOptions options =
            new(agentProvider)
            {
                Configuration = this.Configuration,
                //ConversationId = null, // Assign to continue a conversation
                //LoggerFactory = null, // Assign to enable logging
            };

        return DeclarativeWorkflowBuilder.Build<string>(this.WorkflowFile, options);
    }

    /// <summary>
    /// Configuration key used to identify the Foundry project endpoint.
    /// </summary>
    private const string ConfigKeyFoundryEndpoint = "FOUNDRY_PROJECT_ENDPOINT";

    /// <summary>
    /// Controls on whether the function tools (<see cref="AIFunction"/>) initialized
    /// in the constructor are included for auto-invocation.
    /// NOTE: By default, no functions exist as part of this sample.
    /// </summary>
    private const bool IncludeFunctions = true;

    private static Dictionary<string, string> NameCache { get; } = [];
    private static HashSet<string> FileCache { get; } = [];

    private string WorkflowFile { get; }
    private string? WorkflowInput { get; }
    private string FoundryEndpoint { get; }
    private PersistentAgentsClient FoundryClient { get; }
    private IConfiguration Configuration { get; }
    private CheckpointInfo? LastCheckpoint { get; set; }
    private Dictionary<string, AIFunction> FunctionMap { get; }

    private Program(string workflowFile, string? workflowInput)
    {
        this.WorkflowFile = workflowFile;
        this.WorkflowInput = workflowInput;

        this.Configuration = InitializeConfig();

        this.FoundryEndpoint = this.Configuration[ConfigKeyFoundryEndpoint] ?? throw new InvalidOperationException($"Undefined configuration setting: {ConfigKeyFoundryEndpoint}");
        this.FoundryClient = new PersistentAgentsClient(this.FoundryEndpoint, new AzureCliCredential());

        List<AIFunction> functions =
            [
                // Manually define any custom functions that may be required by agents within the workflow.
                // By default, this sample does not include any functions.
                //AIFunctionFactory.Create(),
            ];
        this.FunctionMap = functions.ToDictionary(f => f.Name);
    }

    private async Task<ExternalRequest?> MonitorAndDisposeWorkflowRunAsync(Checkpointed<StreamingRun> run, object? response = null)
    {
        await using IAsyncDisposable disposeRun = run;

        bool hasStreamed = false;
        string? messageId = null;

        await foreach (WorkflowEvent workflowEvent in run.Run.WatchStreamAsync())
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

                case WorkflowErrorEvent workflowError:
                    throw workflowError.Data as Exception ?? new InvalidOperationException("Unexpected failure...");

                case SuperStepCompletedEvent checkpointCompleted:
                    this.LastCheckpoint = checkpointCompleted.CompletionInfo?.Checkpoint;
                    Debug.WriteLine($"CHECKPOINT x{checkpointCompleted.StepNumber} [{this.LastCheckpoint?.CheckpointId ?? "(none)"}]");
                    break;

                case RequestInfoEvent requestInfo:
                    Debug.WriteLine($"REQUEST #{requestInfo.Request.RequestId}");
                    if (response is not null)
                    {
                        ExternalResponse requestResponse = requestInfo.Request.CreateResponse(response);
                        await run.Run.SendResponseAsync(requestResponse);
                        response = null;
                    }
                    else
                    {
                        await run.Run.DisposeAsync();
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
                        hasStreamed = false;
                        messageId = streamEvent.Update.MessageId;

                        if (messageId is not null)
                        {
                            string? agentId = streamEvent.Update.AgentId;
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
                        case RequiredActionUpdate actionUpdate:
                            Console.ForegroundColor = ConsoleColor.White;
                            Console.Write($"Calling tool: {actionUpdate.FunctionName}");
                            Console.ForegroundColor = ConsoleColor.DarkGray;
                            Console.WriteLine($" [{actionUpdate.ToolCallId}]");
                            break;
                    }
                    try
                    {
                        Console.ResetColor();
                        Console.Write(streamEvent.Update.Text);
                        hasStreamed |= !string.IsNullOrEmpty(streamEvent.Update.Text);
                    }
                    finally
                    {
                        Console.ResetColor();
                    }
                    break;

                case AgentRunResponseEvent messageEvent:
                    try
                    {
                        if (hasStreamed)
                        {
                            Console.WriteLine();
                        }

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

    /// <summary>
    /// Handle request for external input, either from a human or a function tool invocation.
    /// </summary>
    private async ValueTask<object> HandleExternalRequestAsync(ExternalRequest request) =>
        request.Data.TypeId.TypeName switch
        {
            // Request for human input
            _ when request.Data.TypeId.IsMatch<InputRequest>() => HandleInputRequest(request.DataAs<InputRequest>()!),
            // Request for function tool invocation.  (Only active when functions are defined and IncludeFunctions is true.)
            _ when request.Data.TypeId.IsMatch<AgentToolRequest>() => await this.HandleToolRequestAsync(request.DataAs<AgentToolRequest>()!),
            // Unknown request type.
            _ => throw new InvalidOperationException($"Unsupported external request type: {request.GetType().Name}."),
        };

    /// <summary>
    /// Handle request for human input.
    /// </summary>
    private static InputResponse HandleInputRequest(InputRequest request)
    {
        string? userInput;
        do
        {
            Console.ForegroundColor = ConsoleColor.DarkGreen;
            Console.Write($"\n{request.Prompt ?? "INPUT:"} ");
            Console.ForegroundColor = ConsoleColor.White;
            userInput = Console.ReadLine();
        }
        while (string.IsNullOrWhiteSpace(userInput));

        return new InputResponse(userInput);
    }

    /// <summary>
    /// Handle a function tool request by invoking the specified tools and returning the results.
    /// </summary>
    /// <remarks>
    /// This handler is only active when <see cref="IncludeFunctions"/> is set to true and
    /// one or more <see cref="AIFunction"/> instances are defined in the constructor.
    /// </remarks>
    private async ValueTask<AgentToolResponse> HandleToolRequestAsync(AgentToolRequest request)
    {
        Task<FunctionResultContent>[] functionTasks = request.FunctionCalls.Select(functionCall => InvokesToolAsync(functionCall)).ToArray();

        await Task.WhenAll(functionTasks);

        return AgentToolResponse.Create(request, functionTasks.Select(task => task.Result));

        async Task<FunctionResultContent> InvokesToolAsync(FunctionCallContent functionCall)
        {
            AIFunction functionTool = this.FunctionMap[functionCall.Name];
            AIFunctionArguments? functionArguments = functionCall.Arguments is null ? null : new(functionCall.Arguments.NormalizePortableValues());
            object? result = await functionTool.InvokeAsync(functionArguments);
            return new FunctionResultContent(functionCall.CallId, JsonSerializer.Serialize(result));
        }
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
