// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Declarative;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Shared.Foundry;
using Shared.Workflows;

namespace Demo.Workflows.Declarative.AotCheckpointing;

/// <summary>
/// Demonstrates JSON checkpointing of a declarative workflow under reflection-disabled
/// <see cref="System.Text.Json.JsonSerializer"/> (the AOT / trim-aggressive constraint set
/// via <c>JsonSerializerIsReflectionEnabledByDefault=false</c> in the csproj).
/// </summary>
/// <remarks>
/// The key call is <see cref="CheckpointManager.CreateJson(ICheckpointStore{System.Text.Json.JsonElement}, System.Text.Json.JsonSerializerOptions?)"/>
/// with <see cref="DeclarativeWorkflowJsonOptions.Default"/>. Drop the options argument to observe the AOT failure. See README.
/// </remarks>
internal sealed class Program
{
    public static async Task Main(string[] args)
    {
        IConfiguration configuration = Application.InitializeConfig();
        Uri foundryEndpoint = new(configuration.GetValue(Application.Settings.FoundryEndpoint));

        await CreateGreeterAgentAsync(foundryEndpoint, configuration);

        string workflowInput = Application.GetInput(args);

        Workflow CreateWorkflow()
        {
            AzureAgentProvider agentProvider = new(foundryEndpoint, new AzureCliCredential());
            DeclarativeWorkflowOptions options = new(agentProvider) { Configuration = configuration };
            string workflowPath = Path.Combine(AppContext.BaseDirectory, "AotCheckpointing.yaml");
            return DeclarativeWorkflowBuilder.Build<string>(workflowPath, options);
        }

        DirectoryInfo checkpointFolder = Directory.CreateDirectory(Path.Combine(".", $"chk-{DateTime.Now:yyMMdd-HHmmss-ff}"));
        try
        {
            using FileSystemJsonCheckpointStore store = new(checkpointFolder);

            // KEY LINE: AOT-safe checkpoint manager. Drop the options argument to see the failure.
            CheckpointManager checkpointManager = CheckpointManager.CreateJson(store, DeclarativeWorkflowJsonOptions.Default);

            Console.WriteLine($"\nCheckpoint folder: {checkpointFolder.FullName}");

            // Phase 1: run + drain. Every [checkpoint x<n>] line is a successful JSON WRITE.
            List<CheckpointInfo> checkpoints = await RunAndStreamAsync(CreateWorkflow(), workflowInput, checkpointManager).ConfigureAwait(false);

            // Phase 2: prove the JSON READ path. ResumeStreamingAsync deserializes the checkpoint
            // inside the call; a clean return is the proof. We do not drain the resumed run because
            // it parks in WaitForInputAsync without a pending external request.
            if (checkpoints.Count > 0)
            {
                CheckpointInfo resumeFromCheckpoint = checkpoints[0];
                Console.WriteLine($"\nWORKFLOW: Verifying read path by resuming from checkpoint {resumeFromCheckpoint.CheckpointId}");
                StreamingRun resumed = await InProcessExecution.ResumeStreamingAsync(CreateWorkflow(), resumeFromCheckpoint, checkpointManager).ConfigureAwait(false);
                await resumed.DisposeAsync().ConfigureAwait(false);
                Console.WriteLine("WORKFLOW: Checkpoint deserialized successfully");
            }

            Console.WriteLine("\nWORKFLOW: Done!\n");
        }
        finally
        {
            TryDelete(checkpointFolder);
        }
    }

    private static async Task<List<CheckpointInfo>> RunAndStreamAsync(Workflow workflow, string input, CheckpointManager checkpointManager)
    {
        StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, input, checkpointManager).ConfigureAwait(false);
        return await DrainAsync(run).ConfigureAwait(false);
    }

    private static async Task<List<CheckpointInfo>> DrainAsync(StreamingRun run)
    {
#pragma warning disable CA2007 // Consider calling ConfigureAwait on the awaited task
        await using IAsyncDisposable disposeRun = run;
#pragma warning restore CA2007

        List<CheckpointInfo> checkpoints = [];
        string? streamingMessageId = null;

        await foreach (WorkflowEvent workflowEvent in run.WatchStreamAsync().ConfigureAwait(false))
        {
            switch (workflowEvent)
            {
                case WorkflowErrorEvent workflowError:
                    throw workflowError.Data as Exception ?? new InvalidOperationException("Unexpected workflow failure.");

                case SuperStepCompletedEvent superStepCompleted:
                    CheckpointInfo? checkpoint = superStepCompleted.CompletionInfo?.Checkpoint;
                    if (checkpoint is not null)
                    {
                        checkpoints.Add(checkpoint);
                    }
                    Console.ForegroundColor = ConsoleColor.DarkGray;
                    Console.WriteLine($"\n[checkpoint x{superStepCompleted.StepNumber}: {checkpoint?.CheckpointId ?? "(none)"}]");
                    Console.ResetColor();
                    break;

                case MessageActivityEvent activityEvent:
                    Console.ForegroundColor = ConsoleColor.Yellow;
                    Console.WriteLine($"\nACTIVITY: {activityEvent.Message.Trim()}");
                    Console.ResetColor();
                    break;

                case AgentResponseUpdateEvent streamEvent:
                    if (!string.Equals(streamingMessageId, streamEvent.Update.MessageId, StringComparison.Ordinal))
                    {
                        streamingMessageId = streamEvent.Update.MessageId;
                        string agentName = streamEvent.Update.AuthorName ?? streamEvent.Update.AgentId ?? nameof(ChatRole.Assistant);
                        Console.ForegroundColor = ConsoleColor.Cyan;
                        Console.Write($"\n{agentName.ToUpperInvariant()}: ");
                        Console.ResetColor();
                    }
                    Console.Write(streamEvent.Update.Text);
                    break;
            }
        }

        return checkpoints;
    }

    private static async Task CreateGreeterAgentAsync(Uri foundryEndpoint, IConfiguration configuration)
    {
        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
        // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
        AIProjectClient aiProjectClient = new(foundryEndpoint, new DefaultAzureCredential());

        DeclarativeAgentDefinition definition =
            new(configuration.GetValue(Application.Settings.FoundryModel))
            {
                Instructions =
                    """
                    You are a warm and concise greeter. Reply to the user's message in
                    one or two short sentences. Always include the user's name if they
                    provided one, and end with a friendly question.
                    """
            };

        await aiProjectClient.CreateAgentAsync(
            agentName: "GreeterAgent",
            agentDefinition: definition,
            agentDescription: "Greeter agent for the AotCheckpointing sample.");
    }

    private static void TryDelete(DirectoryInfo directory)
    {
        try
        {
            directory.Refresh();
            if (directory.Exists)
            {
                directory.Delete(recursive: true);
            }
        }
        catch (Exception ex)
        {
            Console.ForegroundColor = ConsoleColor.DarkYellow;
            Console.WriteLine($"\n(could not clean up '{directory.FullName}': {ex.Message})");
            Console.ResetColor();
        }
    }
}
