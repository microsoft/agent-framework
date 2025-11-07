// Copyright (c) Microsoft. All rights reserved.

// Uncomment to output unknown content types for debugging.
//#define DEBUG_OUTPUT 

using System.Diagnostics;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Declarative;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

namespace Shared.Workflows;

// Types are for evaluation purposes only and is subject to change or removal in future updates.
#pragma warning disable OPENAI001 
#pragma warning disable OPENAICUA001
#pragma warning disable MEAI001

internal sealed class WorkflowRunner
{
    private Dictionary<string, AIFunction> FunctionMap { get; }
    private CheckpointInfo? LastCheckpoint { get; set; }

    public static void Notify(string message, ConsoleColor? color = null)
    {
        Console.ForegroundColor = color ?? ConsoleColor.Cyan;
        try
        {
            Console.WriteLine(message);
        }
        finally
        {
            Console.ResetColor();
        }
    }

    /// <summary>
    /// When enabled, checkpoints will be persisted to disk as JSON files.
    /// Otherwise  an in-memory checkpoint store that will not persist checkpoints
    /// beyond the lifetime of the process.
    /// </summary>
    public bool UseJsonCheckpoints { get; init; }

    public WorkflowRunner(params IEnumerable<AIFunction> functions)
    {
        this.FunctionMap = functions.ToDictionary(f => f.Name);
    }

    public async Task ExecuteAsync(Func<Workflow> workflowProvider, string input)
    {
        Workflow workflow = workflowProvider.Invoke();

        CheckpointManager checkpointManager;

        if (this.UseJsonCheckpoints)
        {
            // Use a file-system based JSON checkpoint store to persist checkpoints to disk.
            DirectoryInfo checkpointFolder = Directory.CreateDirectory(Path.Combine(".", $"chk-{DateTime.Now:yyMMdd-hhmmss-ff}"));
            checkpointManager = CheckpointManager.CreateJson(new FileSystemJsonCheckpointStore(checkpointFolder));
        }
        else
        {
            // Use an in-memory checkpoint store that will not persist checkpoints beyond the lifetime of the process.
            checkpointManager = CheckpointManager.CreateInMemory();
        }

        Checkpointed<StreamingRun> run = await InProcessExecution.StreamAsync(workflow, input, checkpointManager).ConfigureAwait(false);

        bool isComplete = false;
        ExternalResponse? requestResponse = null;
        do
        {
            ExternalRequest? externalRequest = await this.MonitorAndDisposeWorkflowRunAsync(run, requestResponse).ConfigureAwait(false);
            if (externalRequest is not null)
            {
                Notify("\nWORKFLOW: Yield\n", ConsoleColor.DarkYellow);

                if (this.LastCheckpoint is null)
                {
                    throw new InvalidOperationException("Checkpoint information missing after external request.");
                }

                // Process the external request.
                object response = await this.HandleExternalRequestAsync(externalRequest).ConfigureAwait(false);
                requestResponse = externalRequest.CreateResponse(response);

                // Let's resume on an entirely new workflow instance to demonstrate checkpoint portability.
                workflow = workflowProvider.Invoke();

                // Restore the latest checkpoint.
                Debug.WriteLine($"RESTORE #{this.LastCheckpoint.CheckpointId}");
                Notify("WORKFLOW: Restore", ConsoleColor.DarkYellow);

                run = await InProcessExecution.ResumeStreamAsync(workflow, this.LastCheckpoint, checkpointManager, run.Run.RunId).ConfigureAwait(false);
            }
            else
            {
                isComplete = true;
            }
        }
        while (!isComplete);

        Notify("\nWORKFLOW: Done!\n");
    }

    public async Task<ExternalRequest?> MonitorAndDisposeWorkflowRunAsync(Checkpointed<StreamingRun> run, ExternalResponse? response = null)
    {
#pragma warning disable CA2007 // Consider calling ConfigureAwait on the awaited task
        await using IAsyncDisposable disposeRun = run;
#pragma warning restore CA2007 // Consider calling ConfigureAwait on the awaited task

        bool hasStreamed = false;
        string? messageId = null;

        bool shouldExit = false;
        ExternalRequest? externalResponse = null;

        if (response is not null)
        {
            await run.Run.SendResponseAsync(response).ConfigureAwait(false);
        }

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

                case WorkflowErrorEvent workflowError:
                    throw workflowError.Data as Exception ?? new InvalidOperationException("Unexpected failure...");

                case SuperStepCompletedEvent checkpointCompleted:
                    this.LastCheckpoint = checkpointCompleted.CompletionInfo?.Checkpoint;
                    Debug.WriteLine($"CHECKPOINT x{checkpointCompleted.StepNumber} [{this.LastCheckpoint?.CheckpointId ?? "(none)"}]");
                    if (externalResponse is not null)
                    {
                        shouldExit = true;
                    }
                    break;

                case RequestInfoEvent requestInfo:
                    Debug.WriteLine($"REQUEST #{requestInfo.Request.RequestId}");
                    externalResponse = requestInfo.Request;
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
                            string? agentName = streamEvent.Update.AuthorName ?? streamEvent.Update.AgentId ?? nameof(ChatRole.Assistant);
                            Console.ForegroundColor = ConsoleColor.Cyan;
                            Console.Write($"\n{agentName.ToUpperInvariant()}:");
                            Console.ForegroundColor = ConsoleColor.DarkGray;
                            Console.WriteLine($" [{messageId}]");
                        }
                    }

                    ChatResponseUpdate? chatUpdate = streamEvent.Update.RawRepresentation as ChatResponseUpdate;
                    switch (chatUpdate?.RawRepresentation)
                    {
                        case ImageGenerationCallResponseItem messageUpdate:
                            await DownloadFileContentAsync(Path.GetFileName("response.png"), messageUpdate.ImageResultBytes).ConfigureAwait(false);
                            break;

                        case FunctionCallResponseItem actionUpdate:
                            Console.ForegroundColor = ConsoleColor.White;
                            Console.Write($"Calling tool: {actionUpdate.FunctionName}");
                            Console.ForegroundColor = ConsoleColor.DarkGray;
                            Console.WriteLine($" [{actionUpdate.CallId}]");
                            break;

                        case McpToolCallItem actionUpdate:
                            Console.ForegroundColor = ConsoleColor.White;
                            Console.Write($"Calling tool: {actionUpdate.ToolName}");
                            Console.ForegroundColor = ConsoleColor.DarkGray;
                            Console.WriteLine($" [{actionUpdate.Id}]");
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

                default:
#if DEBUG_OUTPUT
                    Debug.WriteLine($"UNHANDLED: {workflowEvent.GetType().Name}");
#endif
                    break;
            }

            if (shouldExit)
            {
                break;
            }
        }

        return externalResponse;
    }

    /// <summary>
    /// Handle request for external input.
    /// </summary>
    private async ValueTask<ExternalInputResponse> HandleExternalRequestAsync(ExternalRequest request)
    {
        ExternalInputRequest inputRequest =
            request.DataAs<ExternalInputRequest>() ??
            throw new InvalidOperationException($"Expected external request type: {request.GetType().Name}.");

        List<ChatMessage> responseMessages = [];

        foreach (ChatMessage message in inputRequest.AgentResponse.Messages)
        {
            await foreach (ChatMessage responseMessage in this.ProcessInputMessageAsync(message).ConfigureAwait(false))
            {
                responseMessages.Add(responseMessage);
            }
        }

        if (responseMessages.Count == 0)
        {
            // Must be request for user input.
            responseMessages.Add(HandleUserInputRequest(inputRequest));
        }

        Console.WriteLine();

        return new ExternalInputResponse(responseMessages);
    }

    private async IAsyncEnumerable<ChatMessage> ProcessInputMessageAsync(ChatMessage message)
    {
        foreach (AIContent requestItem in message.Contents)
        {
            ChatMessage? responseMessage =
                requestItem switch
                {
                    FunctionCallContent functionCall => await InvokeFunctionAsync(functionCall).ConfigureAwait(false),
                    FunctionApprovalRequestContent functionApprovalRequest => ApproveFunction(functionApprovalRequest),
                    McpServerToolApprovalRequestContent mcpApprovalRequest => ApproveMCP(mcpApprovalRequest),
                    _ => HandleUnknown(requestItem),
                };

            if (responseMessage is not null)
            {
                yield return responseMessage;
            }
        }

        ChatMessage? HandleUnknown(AIContent request)
        {
#if DEBUG_OUTPUT
            Notify($"INPUT - Unknown: {request.GetType().Name} [{request.RawRepresentation?.GetType().Name ?? "*"}]");
#endif
            return null;
        }

        ChatMessage ApproveFunction(FunctionApprovalRequestContent functionApprovalRequest)
        {
            Notify($"INPUT - Approving Function: {functionApprovalRequest.FunctionCall.Name}");
            return new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateResponse(approved: true)]);
        }

        ChatMessage ApproveMCP(McpServerToolApprovalRequestContent mcpApprovalRequest)
        {
            Notify($"INPUT - Approving MCP: {mcpApprovalRequest.ToolCall.ToolName}");
            return new ChatMessage(ChatRole.User, [mcpApprovalRequest.CreateResponse(approved: true)]);
        }

        async Task<ChatMessage> InvokeFunctionAsync(FunctionCallContent functionCall)
        {
            Notify($"INPUT - Executing Function: {functionCall.Name}");
            AIFunction functionTool = this.FunctionMap[functionCall.Name];
            AIFunctionArguments? functionArguments = functionCall.Arguments is null ? null : new(functionCall.Arguments.NormalizePortableValues());
            object? result = await functionTool.InvokeAsync(functionArguments).ConfigureAwait(false);
            return new ChatMessage(ChatRole.Tool, [new FunctionResultContent(functionCall.CallId, JsonSerializer.Serialize(result))]);
        }
    }

    private static ChatMessage HandleUserInputRequest(ExternalInputRequest request)
    {
        string prompt =
            string.IsNullOrWhiteSpace(request.AgentResponse.Text) || request.AgentResponse.ResponseId is not null ?
                "INPUT:" :
                request.AgentResponse.Text;

        string? userInput;
        do
        {
            Console.ForegroundColor = ConsoleColor.DarkGreen;
            Console.Write($"{prompt} ");
            Console.ForegroundColor = ConsoleColor.White;
            userInput = Console.ReadLine();
        }
        while (string.IsNullOrWhiteSpace(userInput));

        return new ChatMessage(ChatRole.User, userInput);
    }

    private static async ValueTask DownloadFileContentAsync(string filename, BinaryData content)
    {
        string filePath = Path.Combine(Path.GetTempPath(), Path.GetFileName(filename));
        filePath = Path.ChangeExtension(filePath, ".png");

        await File.WriteAllBytesAsync(filePath, content.ToArray()).ConfigureAwait(false);

        Process.Start(
            new ProcessStartInfo
            {
                FileName = "cmd.exe",
                Arguments = $"/C start {filePath}"
            });
    }
}
