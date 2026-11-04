// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;
using MeaiTextContent = Microsoft.Extensions.AI.TextContent;
using OpenAIComputerCallOutputResponseItem = OpenAI.Responses.ComputerCallOutputResponseItem;
using OpenAIComputerCallResponseItem = OpenAI.Responses.ComputerCallResponseItem;
using OpenAIContainerFileCitationMessageAnnotation = OpenAI.Responses.ContainerFileCitationMessageAnnotation;
using OpenAIFileCitationMessageAnnotation = OpenAI.Responses.FileCitationMessageAnnotation;
using OpenAIFilePathMessageAnnotation = OpenAI.Responses.FilePathMessageAnnotation;
using OpenAIMessageResponseItem = OpenAI.Responses.MessageResponseItem;
using OpenAIStreamingResponseOutputItemAddedUpdate = OpenAI.Responses.StreamingResponseOutputItemAddedUpdate;
using OpenAIStreamingResponseOutputItemDoneUpdate = OpenAI.Responses.StreamingResponseOutputItemDoneUpdate;
using OpenAIStreamingResponseOutputTextAnnotationAddedUpdate = OpenAI.Responses.StreamingResponseOutputTextAnnotationAddedUpdate;
using OpenAIStreamingResponseOutputTextDeltaUpdate = OpenAI.Responses.StreamingResponseOutputTextDeltaUpdate;
using OpenAIStreamingResponseUpdate = OpenAI.Responses.StreamingResponseUpdate;

namespace Microsoft.Agents.AI.Foundry.Hosting;

internal abstract record OutputConverterItem
{
    public sealed record ResponseEvent(ResponseStreamEvent Event) : OutputConverterItem;

    public sealed record WorkflowCheckpoint(CheckpointInfo Checkpoint) : OutputConverterItem;

    public static implicit operator OutputConverterItem(ResponseStreamEvent value) =>
        new ResponseEvent(value);
}

/// <summary>
/// Converts agent-framework <see cref="AgentResponseUpdate"/> streams into
/// Responses Server SDK <see cref="ResponseStreamEvent"/> sequences using the
/// <see cref="ResponseEventStream"/> builder pattern.
/// </summary>
internal static class OutputConverter
{
    private sealed class PendingMcpCall(
        OutputItemMcpCallBuilder builder,
        LocalMcpExecutionContract contract,
        string arguments)
    {
        public OutputItemMcpCallBuilder Builder { get; } = builder;

        public LocalMcpExecutionContract Contract { get; } = contract;

        public string Arguments { get; } = arguments;
    }

    private sealed record DeferredLocalMcpCall(string FunctionName, string Arguments);

    /// <summary>
    /// Converts a stream of <see cref="AgentResponseUpdate"/> into a stream of
    /// <see cref="ResponseStreamEvent"/> using the SDK builder pattern.
    /// </summary>
    /// <param name="updates">The agent response updates to convert.</param>
    /// <param name="stream">The SDK event stream builder.</param>
    /// <param name="stateBag">Optional session state bag used to persist tool-approval id mappings across turns.</param>
    /// <param name="localMcpFunctions">Locally executed function names and their MCP wire identities.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>
    /// An async enumerable of SDK response stream events. Workflow checkpoint boundaries are omitted.
    /// </returns>
    public static async IAsyncEnumerable<ResponseStreamEvent> ConvertUpdatesToEventsAsync(
        IAsyncEnumerable<AgentResponseUpdate> updates,
        ResponseEventStream stream,
        AgentSessionStateBag? stateBag = null,
        IReadOnlyDictionary<string, LocalMcpExecutionContract>? localMcpFunctions = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await foreach (OutputConverterItem item in ConvertUpdatesToItemsAsync(
            updates,
            stream,
            stateBag,
            localMcpFunctions,
            cancellationToken).ConfigureAwait(false))
        {
            if (item is OutputConverterItem.ResponseEvent responseEvent)
            {
                yield return responseEvent.Event;
            }
        }
    }

    /// <summary>
    /// Converts a stream of <see cref="AgentResponseUpdate"/> into response events and workflow
    /// checkpoint boundaries.
    /// </summary>
    /// <param name="updates">The agent response updates to convert.</param>
    /// <param name="stream">The SDK event stream builder.</param>
    /// <param name="stateBag">Optional session state bag used to persist tool-approval id mappings across turns.</param>
    /// <param name="localMcpFunctions">Locally executed function names and their MCP wire identities.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Converted response events and workflow checkpoint boundaries in source order.</returns>
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing function call arguments dictionary.")]
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing function call arguments dictionary.")]
    public static async IAsyncEnumerable<OutputConverterItem> ConvertUpdatesToItemsAsync(
        IAsyncEnumerable<AgentResponseUpdate> updates,
        ResponseEventStream stream,
        AgentSessionStateBag? stateBag = null,
        IReadOnlyDictionary<string, LocalMcpExecutionContract>? localMcpFunctions = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        ResponseUsage? accumulatedUsage = null;
        OutputItemMessageBuilder? currentMessageBuilder = null;
        TextContentBuilder? currentTextBuilder = null;
        StringBuilder? accumulatedText = null;
        List<Annotation>? accumulatedAnnotations = null;
        string? previousMessageId = null;
        bool hasTerminalEvent = false;
        var executorItemIds = new Dictionary<string, string>();
        var pendingMcpCalls = new Dictionary<string, PendingMcpCall>(StringComparer.Ordinal);
        var deferredLocalMcpCalls = new Dictionary<string, DeferredLocalMcpCall>(StringComparer.Ordinal);

        await foreach (var update in updates.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            cancellationToken.ThrowIfCancellationRequested();

            // Handle workflow events from RawRepresentation.
            // If the update also carries Contents (e.g. WorkflowSession unwrapped a
            // WorkflowErrorEvent or ExecutorFailedEvent into an ErrorContent payload),
            // fall through to the content-processing path below so those are emitted.
            if (update.RawRepresentation is WorkflowEvent workflowEvent && update.Contents.Count == 0)
            {
                // Close any open message builder before emitting workflow items
                foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText, accumulatedAnnotations))
                {
                    yield return evt;
                }

                currentTextBuilder = null;
                currentMessageBuilder = null;
                accumulatedText = null;
                accumulatedAnnotations = null;
                previousMessageId = null;

                foreach (var evt in EmitWorkflowEvent(stream, workflowEvent, executorItemIds))
                {
                    yield return evt;
                }

                if (workflowEvent is SuperStepCompletedEvent
                    {
                        CompletionInfo.Checkpoint: { } checkpoint
                    })
                {
                    yield return new OutputConverterItem.WorkflowCheckpoint(checkpoint);
                }

                continue;
            }

            string? currentMessageId = ResolveMessageId(update);
            // Completed messages retain independent text parts in one update. Provider streaming
            // spans already address the generated text, including when a chunk has multiple parts.
            bool isStreamingUpdate = update.RawRepresentation is ChatResponseUpdate or OpenAIStreamingResponseUpdate;
            int textPartOffset = 0;
            foreach (var content in update.Contents)
            {
                switch (content)
                {
                    case MeaiTextContent textContent:
                    {
                        if (!IsSameMessage(currentMessageId, previousMessageId) && currentMessageBuilder is not null)
                        {
                            foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText, accumulatedAnnotations))
                            {
                                yield return evt;
                            }

                            currentTextBuilder = null;
                            currentMessageBuilder = null;
                            accumulatedText = null;
                            accumulatedAnnotations = null;
                        }

                        if (currentMessageId is { Length: > 0 })
                        {
                            previousMessageId = currentMessageId;
                        }

                        if (currentMessageBuilder is null)
                        {
                            textPartOffset = 0;
                            currentMessageBuilder = stream.AddOutputItemMessage();
                            yield return currentMessageBuilder.EmitAdded();

                            currentTextBuilder = currentMessageBuilder.AddTextContent();
                            yield return currentTextBuilder.EmitAdded();

                            accumulatedText = new StringBuilder();
                        }

                        if (textContent.Text is { Length: > 0 })
                        {
                            accumulatedText!.Append(textContent.Text);
                            yield return currentTextBuilder!.EmitDelta(textContent.Text);
                        }

                        break;
                    }

                    case FunctionCallContent functionCall:
                    {
                        if (functionCall.CallId is not { Length: > 0 })
                        {
                            break;
                        }

                        foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText, accumulatedAnnotations))
                        {
                            yield return evt;
                        }

                        currentTextBuilder = null;
                        currentMessageBuilder = null;
                        accumulatedText = null;
                        accumulatedAnnotations = null;
                        previousMessageId = null;

                        var arguments = functionCall.Arguments is not null
                            ? JsonSerializer.Serialize(functionCall.Arguments)
                            : "{}";

                        if (localMcpFunctions?.TryGetValue(functionCall.Name, out var localMcpFunction) is true)
                        {
                            if (localMcpFunction.DeferProjectionUntilResult)
                            {
                                deferredLocalMcpCalls[functionCall.CallId] =
                                    new DeferredLocalMcpCall(functionCall.Name, arguments);
                                break;
                            }

                            // Approval-required local MCP calls surface only as mcp_approval_request until the
                            // caller approves them. Emitting an mcp_call here would falsely claim execution.
                            if (localMcpFunction.RequiresApproval)
                            {
                                break;
                            }

                            var mcpBuilder = stream.AddOutputItemMcpCall(
                                localMcpFunction.ServerLabel,
                                localMcpFunction.ToolName);
                            LocalMcpCallIdMap.Record(
                                stateBag,
                                mcpBuilder.ItemId,
                                functionCall.CallId,
                                functionCall.Name,
                                localMcpFunction.ToolName,
                                localMcpFunction.ServerLabel);
                            pendingMcpCalls[functionCall.CallId] =
                                new PendingMcpCall(mcpBuilder, localMcpFunction, arguments);

                            yield return mcpBuilder.EmitAdded();
                            yield return mcpBuilder.EmitInProgress();
                            yield return mcpBuilder.EmitArgumentsDelta(arguments);
                            yield return mcpBuilder.EmitArgumentsDone(arguments);
                            break;
                        }

                        foreach (var evt in EmitFunctionCall(
                            stream,
                            functionCall.Name,
                            functionCall.CallId,
                            arguments))
                        {
                            yield return evt;
                        }

                        break;
                    }

                    case McpServerToolCallContent mcpCall:
                    {
                        if (mcpCall.CallId is not { Length: > 0 })
                        {
                            break;
                        }

                        foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText, accumulatedAnnotations))
                        {
                            yield return evt;
                        }

                        currentTextBuilder = null;
                        currentMessageBuilder = null;
                        accumulatedText = null;
                        accumulatedAnnotations = null;
                        previousMessageId = null;

                        string serverLabel = mcpCall.ServerName ?? "mcp";
                        string arguments = mcpCall.Arguments is not null
                            ? JsonSerializer.Serialize(mcpCall.Arguments)
                            : "{}";
                        var contract = new LocalMcpExecutionContract(
                            serverLabel,
                            mcpCall.Name,
                            RequiresApproval: false);
                        var mcpBuilder = stream.AddOutputItemMcpCall(serverLabel, mcpCall.Name);
                        NativeMcpCallIdMap.Record(
                            stateBag,
                            mcpBuilder.ItemId,
                            mcpCall.CallId,
                            mcpCall.Name,
                            serverLabel);
                        if (!pendingMcpCalls.TryAdd(
                            mcpCall.CallId,
                            new PendingMcpCall(mcpBuilder, contract, arguments)))
                        {
                            throw new InvalidOperationException(
                                $"MCP call id '{mcpCall.CallId}' is already active.");
                        }

                        yield return mcpBuilder.EmitAdded();
                        yield return mcpBuilder.EmitInProgress();
                        yield return mcpBuilder.EmitArgumentsDelta(arguments);
                        yield return mcpBuilder.EmitArgumentsDone(arguments);
                        break;
                    }

                    // The MEAI OpenAI Responses client has no dedicated content type for computer calls: it yields a
                    // base ToolCallContent carrying the OpenAI item. Without this case the caller would never see the
                    // call it is expected to execute.
                    case ToolCallContent { RawRepresentation: OpenAIComputerCallResponseItem computerCall } computerCallContent:
                    {
                        if (computerCallContent.CallId is not { Length: > 0 })
                        {
                            break;
                        }

                        foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText, accumulatedAnnotations))
                        {
                            yield return evt;
                        }

                        currentTextBuilder = null;
                        currentMessageBuilder = null;
                        accumulatedText = null;
                        accumulatedAnnotations = null;
                        previousMessageId = null;

                        // Emit a fully populated item through the generic builder. The SDK's OutputItemComputerCall
                        // convenience method takes a single action and cannot carry the GA actions batch.
                        var computerCallBuilder = stream.AddOutputItemComputerCall();
                        var computerCallItem = ComputerToolItemConverter.ToOutputItem(computerCall, computerCallBuilder.ItemId);
                        yield return computerCallBuilder.EmitAdded(computerCallItem);
                        yield return computerCallBuilder.EmitDone(computerCallItem);
                        break;
                    }

                    // Only an agent that runs the actions itself produces this; the usual caller-executed loop receives
                    // the output as request input instead. Emitting it keeps the AgentServer history complete.
                    case ToolResultContent { RawRepresentation: OpenAIComputerCallOutputResponseItem computerCallOutput } computerCallOutputContent:
                    {
                        if (computerCallOutputContent.CallId is not { Length: > 0 })
                        {
                            break;
                        }

                        foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText, accumulatedAnnotations))
                        {
                            yield return evt;
                        }

                        currentTextBuilder = null;
                        currentMessageBuilder = null;
                        accumulatedText = null;
                        accumulatedAnnotations = null;
                        previousMessageId = null;

                        var computerCallOutputBuilder = stream.AddOutputItemComputerCallOutput();
                        var computerCallOutputItem = ComputerToolItemConverter.ToOutputItem(computerCallOutput, computerCallOutputBuilder.ItemId);
                        yield return computerCallOutputBuilder.EmitAdded(computerCallOutputItem);
                        yield return computerCallOutputBuilder.EmitDone(computerCallOutputItem);
                        break;
                    }

                    case TextReasoningContent reasoningContent:
                    {
                        foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText, accumulatedAnnotations))
                        {
                            yield return evt;
                        }

                        currentTextBuilder = null;
                        currentMessageBuilder = null;
                        accumulatedText = null;
                        accumulatedAnnotations = null;
                        previousMessageId = null;

                        var reasoningBuilder = stream.AddOutputItemReasoningItem();
                        yield return reasoningBuilder.EmitAdded();

                        var summaryPart = reasoningBuilder.AddSummaryPart();
                        yield return summaryPart.EmitAdded();

                        var text = reasoningContent.Text ?? string.Empty;
                        yield return summaryPart.EmitTextDelta(text);
                        yield return summaryPart.EmitTextDone(text);
                        yield return summaryPart.EmitDone();

                        yield return reasoningBuilder.EmitDone();
                        break;
                    }

                    case ToolApprovalRequestContent approvalRequest when approvalRequest.ToolCall is FunctionCallContent approvalFunctionCall:
                    {
                        foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText, accumulatedAnnotations))
                        {
                            yield return evt;
                        }

                        currentTextBuilder = null;
                        currentMessageBuilder = null;
                        accumulatedText = null;
                        accumulatedAnnotations = null;
                        previousMessageId = null;

                        // The Responses API only standardizes the MCP-flavored approval primitive.
                        // We emit the AF tool-approval request as `mcp_approval_request` with
                        // server_label="agent_framework" — declaring the AF runtime as the virtual
                        // server holding this call. The SDK requires a strict {prefix}_{50hex}
                        // wire-id format, so we hash the AF RequestId and persist the
                        // wireId↔afRequestId mapping in the session state bag for later lookup
                        // when the matching `mcp_approval_response` arrives on a subsequent turn.
                        var wireId = ToolApprovalIdMap.ComputeWireId(approvalRequest.RequestId);

                        var approvalArguments = approvalFunctionCall.Arguments is not null
                            ? JsonSerializer.Serialize(approvalFunctionCall.Arguments)
                            : "{}";
                        LocalMcpExecutionContract? localMcpFunction = null;
                        _ = localMcpFunctions?.TryGetValue(approvalFunctionCall.Name, out localMcpFunction);

                        ToolApprovalIdMap.Record(
                            stateBag,
                            wireId,
                            approvalRequest.RequestId,
                            approvalFunctionCall.CallId,
                            approvalFunctionCall.Name,
                            approvalArguments,
                            localMcpFunction?.ServerLabel,
                            localMcpFunction?.ToolName);

                        var approvalItem = new OutputItemMcpApprovalRequest(
                            wireId,
                            localMcpFunction?.ServerLabel ?? "agent_framework",
                            localMcpFunction?.ToolName ?? approvalFunctionCall.Name,
                            approvalArguments);

                        var approvalBuilder = stream.AddOutputItem<OutputItemMcpApprovalRequest>(wireId);
                        yield return approvalBuilder.EmitAdded(approvalItem);
                        yield return approvalBuilder.EmitDone(approvalItem);
                        break;
                    }

                    case ToolApprovalRequestContent approvalRequest when approvalRequest.ToolCall is McpServerToolCallContent approvalMcpCall:
                    {
                        foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText, accumulatedAnnotations))
                        {
                            yield return evt;
                        }

                        currentTextBuilder = null;
                        currentMessageBuilder = null;
                        accumulatedText = null;
                        accumulatedAnnotations = null;
                        previousMessageId = null;

                        string wireId = ToolApprovalIdMap.ComputeWireId(approvalRequest.RequestId);
                        string serverLabel = approvalMcpCall.ServerName ?? "mcp";
                        string arguments = approvalMcpCall.Arguments is not null
                            ? JsonSerializer.Serialize(approvalMcpCall.Arguments)
                            : "{}";
                        ToolApprovalIdMap.Record(
                            stateBag,
                            wireId,
                            approvalRequest.RequestId,
                            approvalMcpCall.CallId,
                            approvalMcpCall.Name,
                            arguments,
                            serverLabel,
                            approvalMcpCall.Name,
                            isMcpToolCall: true);

                        var approvalItem = new OutputItemMcpApprovalRequest(
                            wireId,
                            serverLabel,
                            approvalMcpCall.Name,
                            arguments);
                        var approvalBuilder = stream.AddOutputItem<OutputItemMcpApprovalRequest>(wireId);
                        yield return approvalBuilder.EmitAdded(approvalItem);
                        yield return approvalBuilder.EmitDone(approvalItem);
                        break;
                    }

                    case ToolApprovalRequestContent:
                        // Approval requests must wrap a supported function or MCP tool call.
                        // Any other shape has no representation in the Responses wire format.
                        break;

                    case ToolApprovalResponseContent:
                        // Approval responses originate from the client and travel inbound; the
                        // workflow does not re-emit them. Skip silently if encountered.
                        break;

                    case UsageContent usageContent when usageContent.Details is not null:
                    {
                        accumulatedUsage = ConvertUsage(usageContent.Details, accumulatedUsage);
                        break;
                    }

                    case ErrorContent errorContent:
                    {
                        foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText, accumulatedAnnotations))
                        {
                            yield return evt;
                        }

                        currentTextBuilder = null;
                        currentMessageBuilder = null;
                        accumulatedText = null;
                        accumulatedAnnotations = null;
                        previousMessageId = null;
                        hasTerminalEvent = true;

                        foreach (var pending in pendingMcpCalls.Values)
                        {
                            yield return pending.Builder.EmitFailed();
                            var item = new OutputItemMcpToolCall(
                                pending.Builder.ItemId,
                                pending.Contract.ServerLabel,
                                pending.Contract.ToolName,
                                pending.Arguments)
                            {
                                Output = string.Empty,
                                Status = MCPToolCallStatus.Failed,
                            };
                            item.Error["message"] = BinaryData.FromObjectAsJson(
                                errorContent.Message ?? "An error occurred during agent execution.");
                            yield return pending.Builder.EmitDone(item);
                        }

                        pendingMcpCalls.Clear();
                        yield return stream.EmitFailed(
                            ResponseErrorCode.ServerError,
                            errorContent.Message ?? "An error occurred during agent execution.",
                            accumulatedUsage);
                        yield break;
                    }

                    case DataContent:
                    case UriContent:
                        // Image/audio/file content from agents is not currently supported
                        // as streaming output items in the Responses Server SDK builder pattern.
                        // These would need to be serialized as base64 or URL references.
                        break;

                    case FunctionResultContent functionResult:
                    {
                        if (functionResult.CallId is not { Length: > 0 })
                        {
                            break;
                        }

                        foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText, accumulatedAnnotations))
                        {
                            yield return evt;
                        }

                        currentTextBuilder = null;
                        currentMessageBuilder = null;
                        accumulatedText = null;
                        accumulatedAnnotations = null;
                        previousMessageId = null;

                        _ = deferredLocalMcpCalls.Remove(
                            functionResult.CallId,
                            out DeferredLocalMcpCall? deferredFunctionCall);
                        bool consentInterrupted = IsConsentInterruptedResult(functionResult);

                        if (!pendingMcpCalls.Remove(
                            functionResult.CallId,
                            out PendingMcpCall? pendingMcpCall))
                        {
                            var approvalEntry = ToolApprovalIdMap.ConsumeMcpEntryByCallId(
                                stateBag,
                                functionResult.CallId,
                                isMcpToolCall: false);
                            if (approvalEntry?.Approved is false)
                            {
                                // A rejected approval produces a synthetic function result for the inner
                                // model transcript. It is not an MCP execution and must not become mcp_call.
                                break;
                            }

                            if (approvalEntry is
                                {
                                    Approved: true,
                                    McpServerLabel: { Length: > 0 } serverLabel,
                                    Name: { Length: > 0 } name
                                })
                            {
                                var arguments = approvalEntry.Arguments ?? "{}";
                                if (consentInterrupted)
                                {
                                    deferredFunctionCall ??= new DeferredLocalMcpCall(name, arguments);
                                }
                                else
                                {
                                    string toolName = approvalEntry.McpToolName ?? name;
                                    var contract = new LocalMcpExecutionContract(
                                        serverLabel,
                                        toolName,
                                        RequiresApproval: true);
                                    var mcpBuilder = stream.AddOutputItemMcpCall(serverLabel, toolName);
                                    LocalMcpCallIdMap.Record(
                                        stateBag,
                                        mcpBuilder.ItemId,
                                        functionResult.CallId,
                                        name,
                                        toolName,
                                        serverLabel);
                                    pendingMcpCall = new PendingMcpCall(mcpBuilder, contract, arguments);

                                    yield return mcpBuilder.EmitAdded();
                                    yield return mcpBuilder.EmitInProgress();
                                    yield return mcpBuilder.EmitArgumentsDelta(arguments);
                                    yield return mcpBuilder.EmitArgumentsDone(arguments);
                                }
                            }
                        }
                        if (pendingMcpCall is null
                            && LocalMcpInvocationMap.Consume(stateBag, functionResult.CallId) is { } invocation)
                        {
                            if (consentInterrupted)
                            {
                                deferredFunctionCall ??= new DeferredLocalMcpCall(
                                    invocation.FunctionName,
                                    invocation.Arguments);
                            }
                            else
                            {
                                var contract = new LocalMcpExecutionContract(
                                    invocation.ServerLabel,
                                    invocation.ToolName,
                                    RequiresApproval: true);
                                var mcpBuilder = stream.AddOutputItemMcpCall(
                                    invocation.ServerLabel,
                                    invocation.ToolName);
                                LocalMcpCallIdMap.Record(
                                    stateBag,
                                    mcpBuilder.ItemId,
                                    functionResult.CallId,
                                    invocation.FunctionName,
                                    invocation.ToolName,
                                    invocation.ServerLabel);
                                pendingMcpCall = new PendingMcpCall(
                                    mcpBuilder,
                                    contract,
                                    invocation.Arguments);

                                yield return mcpBuilder.EmitAdded();
                                yield return mcpBuilder.EmitInProgress();
                                yield return mcpBuilder.EmitArgumentsDelta(invocation.Arguments);
                                yield return mcpBuilder.EmitArgumentsDone(invocation.Arguments);
                            }
                        }

                        if (pendingMcpCall is not null)
                        {
                            _ = LocalMcpInvocationMap.Consume(stateBag, functionResult.CallId);
                            string output = ConvertFunctionResultToText(functionResult.Result);
                            bool failed = functionResult.Exception is not null;
                            yield return failed
                                ? pendingMcpCall.Builder.EmitFailed()
                                : pendingMcpCall.Builder.EmitCompleted();

                            var item = new OutputItemMcpToolCall(
                                pendingMcpCall.Builder.ItemId,
                                pendingMcpCall.Contract.ServerLabel,
                                pendingMcpCall.Contract.ToolName,
                                pendingMcpCall.Arguments)
                            {
                                Output = output,
                                Status = failed ? MCPToolCallStatus.Failed : MCPToolCallStatus.Completed,
                            };
                            if (functionResult.Exception is not null)
                            {
                                item.Error["message"] = BinaryData.FromObjectAsJson(functionResult.Exception.Message);
                            }

                            yield return pendingMcpCall.Builder.EmitDone(item);
                            break;
                        }

                        if (deferredFunctionCall is not null)
                        {
                            foreach (var evt in EmitFunctionCall(
                                stream,
                                deferredFunctionCall.FunctionName,
                                functionResult.CallId,
                                deferredFunctionCall.Arguments))
                            {
                                yield return evt;
                            }
                        }

                        var outputText = EncodeFunctionResultAsJsonStringPayload(functionResult.Result);

                        // Use the SDK's convenience method so the OutputItemFunctionToolCallOutput
                        // is constructed with a populated Id. The public OutputItemFunctionToolCallOutput
                        // ctor only sets CallId/Output (Id is read-only), and AddOutputItem<T>+EmitAdded
                        // does not auto-stamp Id — only ResponseId/AgentReference. Without this, the
                        // serialized item arrives at the Foundry storage layer with id=null and is
                        // rejected with "ID cannot be null or empty (Parameter 'id')".
                        foreach (var evt in stream.OutputItemFunctionCallOutput(
                            functionResult.CallId,
                            BinaryData.FromString(outputText)))
                        {
                            yield return evt;
                        }

                        break;
                    }

                    case McpServerToolResultContent mcpResult:
                    {
                        if (mcpResult.CallId is not { Length: > 0 })
                        {
                            break;
                        }

                        foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText, accumulatedAnnotations))
                        {
                            yield return evt;
                        }

                        currentTextBuilder = null;
                        currentMessageBuilder = null;
                        accumulatedText = null;
                        accumulatedAnnotations = null;
                        previousMessageId = null;

                        if (!pendingMcpCalls.Remove(mcpResult.CallId, out PendingMcpCall? pendingMcpCall))
                        {
                            var approvalEntry = ToolApprovalIdMap.ConsumeMcpEntryByCallId(
                                stateBag,
                                mcpResult.CallId,
                                isMcpToolCall: true);
                            if (approvalEntry?.Approved is false)
                            {
                                break;
                            }

                            if (approvalEntry is
                                {
                                    Approved: true,
                                    McpServerLabel: { Length: > 0 } serverLabel,
                                    Name: { Length: > 0 } name
                                })
                            {
                                string toolName = approvalEntry.McpToolName ?? name;
                                string arguments = approvalEntry.Arguments ?? "{}";
                                var contract = new LocalMcpExecutionContract(
                                    serverLabel,
                                    toolName,
                                    RequiresApproval: true);
                                var mcpBuilder = stream.AddOutputItemMcpCall(serverLabel, toolName);
                                NativeMcpCallIdMap.Record(
                                    stateBag,
                                    mcpBuilder.ItemId,
                                    mcpResult.CallId,
                                    toolName,
                                    serverLabel);
                                pendingMcpCall = new PendingMcpCall(mcpBuilder, contract, arguments);

                                yield return mcpBuilder.EmitAdded();
                                yield return mcpBuilder.EmitInProgress();
                                yield return mcpBuilder.EmitArgumentsDelta(arguments);
                                yield return mcpBuilder.EmitArgumentsDone(arguments);
                            }
                        }

                        if (pendingMcpCall is null)
                        {
                            throw new InvalidOperationException(
                                $"No MCP call was recorded for result '{mcpResult.CallId}'.");
                        }

                        string output = ConvertMcpResultToText(mcpResult.Outputs);
                        yield return pendingMcpCall.Builder.EmitCompleted();
                        var item = new OutputItemMcpToolCall(
                            pendingMcpCall.Builder.ItemId,
                            pendingMcpCall.Contract.ServerLabel,
                            pendingMcpCall.Contract.ToolName,
                            pendingMcpCall.Arguments)
                        {
                            Output = output,
                            Status = MCPToolCallStatus.Completed,
                        };
                        yield return pendingMcpCall.Builder.EmitDone(item);
                        break;
                    }

                    default:
                        break;
                }

                var isTextContent = content is MeaiTextContent;
                var isAnnotationOnlyContentForCurrentMessage =
                    content.GetType() == typeof(AIContent) &&
                    IsSameAnnotationMessage(currentMessageId, previousMessageId);

                // MEAI OpenAI sends streaming citations in a separate annotation-only AIContent after
                // the text deltas. Accumulate them because AgentServer emits annotations only after
                // output_text.done, and de-duplicate providers that report the same citation twice.
                if ((isTextContent || isAnnotationOnlyContentForCurrentMessage)
                    && content.Annotations is { Count: > 0 }
                    && currentMessageBuilder is not null)
                {
                    foreach (var sdkAnnotation in ConvertToSdkAnnotations(content.Annotations, isTextContent ? textPartOffset : 0))
                    {
                        if (accumulatedAnnotations?.Any(existing => AreEquivalentAnnotations(existing, sdkAnnotation)) is not true)
                        {
                            (accumulatedAnnotations ??= []).Add(sdkAnnotation);
                        }
                    }
                }

                if (!isStreamingUpdate && content is MeaiTextContent textPart)
                {
                    textPartOffset += textPart.Text.Length;
                }
            }
        }

        // Close any remaining open message
        foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText, accumulatedAnnotations))
        {
            yield return evt;
        }

        foreach (var pending in pendingMcpCalls.Values)
        {
            yield return pending.Builder.EmitFailed();
            var item = new OutputItemMcpToolCall(
                pending.Builder.ItemId,
                pending.Contract.ServerLabel,
                pending.Contract.ToolName,
                pending.Arguments)
            {
                Output = string.Empty,
                Status = MCPToolCallStatus.Failed,
            };
            item.Error["message"] = BinaryData.FromObjectAsJson("Tool execution did not produce a result.");
            yield return pending.Builder.EmitDone(item);
        }

        if (!hasTerminalEvent)
        {
            yield return stream.EmitCompleted(accumulatedUsage);
        }
    }

    private static IEnumerable<ResponseStreamEvent> CloseCurrentMessage(
        OutputItemMessageBuilder? messageBuilder,
        TextContentBuilder? textBuilder,
        StringBuilder? accumulatedText,
        List<Annotation>? annotations = null)
    {
        if (messageBuilder is null)
        {
            yield break;
        }

        if (textBuilder is not null)
        {
            var finalText = accumulatedText?.ToString() ?? string.Empty;
            yield return textBuilder.EmitTextDone(finalText);

            // Annotations must be emitted after EmitTextDone and before EmitDone.
            if (annotations is not null)
            {
                foreach (var annotation in annotations)
                {
                    yield return textBuilder.EmitAnnotationAdded(annotation);
                }
            }

            yield return textBuilder.EmitDone();
        }

        yield return messageBuilder.EmitDone();
    }

    private static bool IsSameMessage(string? currentId, string? previousId) =>
        currentId is not { Length: > 0 } || previousId is not { Length: > 0 } || currentId == previousId;

    private static bool IsSameAnnotationMessage(string? currentId, string? previousId) =>
        currentId is { Length: > 0 }
            ? currentId == previousId
            : previousId is not { Length: > 0 };

    private static string? ResolveMessageId(AgentResponseUpdate update)
    {
        if (update.MessageId is { Length: > 0 })
        {
            return update.MessageId;
        }

        object? rawRepresentation = update.RawRepresentation is ChatResponseUpdate chatUpdate
            ? chatUpdate.RawRepresentation
            : update.RawRepresentation;

        return rawRepresentation switch
        {
            OpenAIStreamingResponseOutputTextAnnotationAddedUpdate annotationAdded => annotationAdded.ItemId,
            OpenAIStreamingResponseOutputTextDeltaUpdate textDelta => textDelta.ItemId,
            OpenAIStreamingResponseOutputItemAddedUpdate { Item: OpenAIMessageResponseItem message } => message.Id,
            OpenAIStreamingResponseOutputItemDoneUpdate { Item: OpenAIMessageResponseItem message } => message.Id,
            _ => null,
        };
    }

    private static bool AreEquivalentAnnotations(Annotation left, Annotation right) =>
        (left, right) switch
        {
            (UrlCitationBody leftUrl, UrlCitationBody rightUrl) =>
                leftUrl.Url == rightUrl.Url &&
                leftUrl.StartIndex == rightUrl.StartIndex &&
                leftUrl.EndIndex == rightUrl.EndIndex &&
                leftUrl.Title == rightUrl.Title,
            (FileCitationBody leftFile, FileCitationBody rightFile) =>
                leftFile.FileId == rightFile.FileId &&
                leftFile.Index == rightFile.Index &&
                leftFile.Filename == rightFile.Filename,
            (ContainerFileCitationBody leftContainerFile, ContainerFileCitationBody rightContainerFile) =>
                leftContainerFile.ContainerId == rightContainerFile.ContainerId &&
                leftContainerFile.FileId == rightContainerFile.FileId &&
                leftContainerFile.StartIndex == rightContainerFile.StartIndex &&
                leftContainerFile.EndIndex == rightContainerFile.EndIndex &&
                leftContainerFile.Filename == rightContainerFile.Filename,
            (FilePath leftFilePath, FilePath rightFilePath) =>
                leftFilePath.FileId == rightFilePath.FileId &&
                leftFilePath.Index == rightFilePath.Index,
            _ => false,
        };

    /// <summary>
    /// Converts MEAI <see cref="AIAnnotation"/> instances to Responses SDK <see cref="Annotation"/> objects.
    /// Only supported <see cref="CitationAnnotation"/> shapes are converted; all others are skipped.
    /// </summary>
    private static IEnumerable<Annotation> ConvertToSdkAnnotations(IList<AIAnnotation> annotations, int textPartOffset)
    {
        foreach (var ann in annotations)
        {
            if (ann is not CitationAnnotation citation)
            {
                continue;
            }

            if (citation.RawRepresentation is OpenAIContainerFileCitationMessageAnnotation containerFileCitation)
            {
                yield return new ContainerFileCitationBody(
                    containerFileCitation.ContainerId,
                    containerFileCitation.FileId,
                    containerFileCitation.StartIndex,
                    containerFileCitation.EndIndex,
                    containerFileCitation.Filename);
                continue;
            }

            if (citation.RawRepresentation is OpenAIFileCitationMessageAnnotation fileCitation)
            {
                yield return new FileCitationBody(fileCitation.FileId, fileCitation.Index, fileCitation.Filename);
                continue;
            }

            if (citation.RawRepresentation is OpenAIFilePathMessageAnnotation filePath)
            {
                yield return new FilePath(filePath.FileId, filePath.Index);
                continue;
            }

            if (citation.Url is null)
            {
                continue;
            }

            var regions = citation.AnnotatedRegions?
                .OfType<TextSpanAnnotatedRegion>()
                .Where(r => r.StartIndex is not null && r.EndIndex is not null)
                .ToList();

            if (regions is not { Count: > 0 })
            {
                continue;
            }

            foreach (var region in regions)
            {
                yield return new UrlCitationBody(
                    citation.Url,
                    region.StartIndex!.Value + textPartOffset,
                    region.EndIndex!.Value + textPartOffset,
                    citation.Title ?? string.Empty);
            }
        }
    }

    private static ResponseUsage ConvertUsage(UsageDetails details, ResponseUsage? existing)
    {
        var inputTokens = details.InputTokenCount ?? 0;
        var outputTokens = details.OutputTokenCount ?? 0;
        var totalTokens = details.TotalTokenCount ?? 0;

        // Prefer the dedicated counters, retaining the legacy dictionary keys as a fallback.
        var cachedTokens = details.CachedInputTokenCount ??
            (details.AdditionalCounts?.TryGetValue("InputTokenDetails.CachedTokenCount", out var cached) is true ? cached : 0);
        var reasoningTokens = details.ReasoningTokenCount ??
            (details.AdditionalCounts?.TryGetValue("OutputTokenDetails.ReasoningTokenCount", out var reasoning) is true ? reasoning : 0);

        if (existing is not null)
        {
            inputTokens += existing.InputTokens;
            outputTokens += existing.OutputTokens;
            totalTokens += existing.TotalTokens;
            cachedTokens += existing.InputTokensDetails?.CachedTokens ?? 0;
            reasoningTokens += existing.OutputTokensDetails?.ReasoningTokens ?? 0;
        }

        return new ResponseUsage(
            inputTokens: inputTokens,
            inputTokensDetails: new ResponseUsageInputTokensDetails(cachedTokens),
            outputTokens: outputTokens,
            outputTokensDetails: new ResponseUsageOutputTokensDetails(reasoningTokens),
            totalTokens: totalTokens);
    }

    private static IEnumerable<ResponseStreamEvent> EmitWorkflowEvent(
        ResponseEventStream stream,
        WorkflowEvent workflowEvent,
        Dictionary<string, string> executorItemIds)
    {
        switch (workflowEvent)
        {
            case ExecutorInvokedEvent invokedEvent:
            {
                var itemId = GenerateItemId("wfa");
                executorItemIds[invokedEvent.ExecutorId] = itemId;

                var item = new WorkflowActionOutputItem(
                    kind: "InvokeExecutor",
                    actionId: invokedEvent.ExecutorId,
                    status: WorkflowActionOutputItemStatus.InProgress,
                    id: itemId);

                var builder = stream.AddOutputItem<WorkflowActionOutputItem>(itemId);
                yield return builder.EmitAdded(item);
                yield return builder.EmitDone(item);
                break;
            }

            case ExecutorCompletedEvent completedEvent:
            {
                var itemId = GenerateItemId("wfa");

                var item = new WorkflowActionOutputItem(
                    kind: "InvokeExecutor",
                    actionId: completedEvent.ExecutorId,
                    status: WorkflowActionOutputItemStatus.Completed,
                    id: itemId);

                var builder = stream.AddOutputItem<WorkflowActionOutputItem>(itemId);
                yield return builder.EmitAdded(item);
                yield return builder.EmitDone(item);
                executorItemIds.Remove(completedEvent.ExecutorId);
                break;
            }

            case ExecutorFailedEvent failedEvent:
            {
                var itemId = GenerateItemId("wfa");

                var item = new WorkflowActionOutputItem(
                    kind: "InvokeExecutor",
                    actionId: failedEvent.ExecutorId,
                    status: WorkflowActionOutputItemStatus.Failed,
                    id: itemId);

                var builder = stream.AddOutputItem<WorkflowActionOutputItem>(itemId);
                yield return builder.EmitAdded(item);
                yield return builder.EmitDone(item);
                executorItemIds.Remove(failedEvent.ExecutorId);
                break;
            }

            // Informational/lifecycle events — no SDK output needed.
            // Note: AgentResponseUpdateEvent and WorkflowErrorEvent are unwrapped by
            // WorkflowSession.InvokeStageAsync() into regular AgentResponseUpdate objects
            // with populated Contents (TextContent, ErrorContent, etc.), so they flow
            // through the normal content processing path above — not through this method.
            case SuperStepStartedEvent:
            case SuperStepCompletedEvent:
            case WorkflowStartedEvent:
            case WorkflowWarningEvent:
            case RequestInfoEvent:
                break;
        }
    }

    private static IEnumerable<ResponseStreamEvent> EmitFunctionCall(
        ResponseEventStream stream,
        string functionName,
        string callId,
        string arguments)
    {
        var builder = stream.AddOutputItemFunctionCall(functionName, callId);
        yield return builder.EmitAdded();
        yield return builder.EmitArgumentsDelta(arguments);
        yield return builder.EmitArgumentsDone(arguments);
        yield return builder.EmitDone();
    }

    private static bool IsConsentInterruptedResult(FunctionResultContent result)
    {
        if (result.Result is not string text
            || McpConsentContext.Current.Value is not
            {
                HasPendingConsents: true,
            } consentState)
        {
            return false;
        }

        return string.Equals(text, McpConsentResults.ConsentRequired, StringComparison.Ordinal)
            || string.Equals(text, consentState.InterruptedToolResult, StringComparison.Ordinal);
    }

    /// <summary>
    /// Generates a valid item ID matching the SDK's <c>{prefix}_{50chars}</c> format.
    /// </summary>
    private static string GenerateItemId(string prefix)
    {
        // SDK format: {prefix}_{50 char body}
        var bytes = RandomNumberGenerator.GetBytes(25);
        var body = Convert.ToHexString(bytes); // 50 hex chars, uppercase
        return $"{prefix}_{body}";
    }

    /// <summary>
    /// Encodes a <see cref="FunctionResultContent.Result"/> value into the wire payload for
    /// the OpenAI Responses <c>function_call_output.output</c> field.
    /// </summary>
    /// <remarks>
    /// The OpenAI Responses spec requires <c>output</c> to be a JSON string. The Responses
    /// SDK's <see cref="OutputItemFunctionToolCallOutput"/> accepts a <see cref="BinaryData"/>
    /// containing the *raw JSON value* for the field, so the returned text is always a JSON
    /// string literal (quoted, with escapes). This avoids two bugs:
    /// <list type="bullet">
    ///   <item>Complex results (e.g. <c>List&lt;TodoItem&gt;</c>) landing on the wire as an
    ///   unquoted JSON array, which the strict-parsing OpenAI .NET client
    ///   (<c>FunctionCallOutputResponseItem</c>) rejects with
    ///   "requires an element of type 'String', but the target element has type 'Array'".</item>
    ///   <item>Numeric- or JSON-shaped string results (e.g. <c>"42"</c> or <c>"{\"k\":1}"</c>)
    ///   silently changing type on the wire because <c>BinaryData</c> auto-detects JSON.</item>
    /// </list>
    /// <see cref="JsonElement"/> / <see cref="JsonDocument"/> values are unwrapped first so
    /// a string-kind element does not get double-encoded into <c>"\"value\""</c>.
    /// </remarks>
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing function call result payload.")]
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing function call result payload.")]
    internal static string EncodeFunctionResultAsJsonStringPayload(object? result) =>
        JsonSerializer.Serialize(ConvertFunctionResultToText(result));

    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing function call result payload.")]
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing function call result payload.")]
    private static string ConvertFunctionResultToText(object? result)
    {
        return result switch
        {
            null => string.Empty,
            string s => s,
            JsonElement je => je.ValueKind == JsonValueKind.String
                ? (je.GetString() ?? string.Empty)
                : je.GetRawText(),
            JsonDocument jd => jd.RootElement.ValueKind == JsonValueKind.String
                ? (jd.RootElement.GetString() ?? string.Empty)
                : jd.RootElement.GetRawText(),
            _ => JsonSerializer.Serialize(result),
        };
    }

    private static string ConvertMcpResultToText(IList<AIContent>? outputs)
    {
        if (outputs is not { Count: > 0 })
        {
            return string.Empty;
        }

        return string.Join(
            "\n",
            outputs.Select(static output => output switch
            {
                MeaiTextContent text => text.Text,
                DataContent data => data.Uri,
                UriContent uri => uri.Uri.ToString(),
                _ => output.ToString(),
            }));
    }
}
