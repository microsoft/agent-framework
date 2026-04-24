// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
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

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Converts agent-framework <see cref="AgentResponseUpdate"/> streams into
/// Responses Server SDK <see cref="ResponseStreamEvent"/> sequences using the
/// <see cref="ResponseEventStream"/> builder pattern.
/// </summary>
internal static class OutputConverter
{
    /// <summary>
    /// Converts a stream of <see cref="AgentResponseUpdate"/> into a stream of
    /// <see cref="ResponseStreamEvent"/> using the SDK builder pattern.
    /// </summary>
    /// <param name="updates">The agent response updates to convert.</param>
    /// <param name="stream">The SDK event stream builder.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>An async enumerable of SDK response stream events (excluding lifecycle events).</returns>
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing function call arguments dictionary.")]
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing function call arguments dictionary.")]
    public static async IAsyncEnumerable<ResponseStreamEvent> ConvertUpdatesToEventsAsync(
        IAsyncEnumerable<AgentResponseUpdate> updates,
        ResponseEventStream stream,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        ResponseUsage? accumulatedUsage = null;
        OutputItemMessageBuilder? currentMessageBuilder = null;
        TextContentBuilder? currentTextBuilder = null;
        StringBuilder? accumulatedText = null;
        string? previousMessageId = null;
        bool hasTerminalEvent = false;
        var executorItemIds = new Dictionary<string, string>();

        await foreach (var update in updates.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            cancellationToken.ThrowIfCancellationRequested();

            // Handle workflow events from RawRepresentation
            if (update.RawRepresentation is WorkflowEvent workflowEvent)
            {
                // Close any open message builder before emitting workflow items
                foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText))
                {
                    yield return evt;
                }

                currentTextBuilder = null;
                currentMessageBuilder = null;
                accumulatedText = null;
                previousMessageId = null;

                foreach (var evt in EmitWorkflowEvent(stream, workflowEvent, executorItemIds))
                {
                    yield return evt;
                }

                continue;
            }

            foreach (var content in update.Contents)
            {
                switch (content)
                {
                    case MeaiTextContent textContent:
                    {
                        if (!IsSameMessage(update.MessageId, previousMessageId) && currentMessageBuilder is not null)
                        {
                            foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText))
                            {
                                yield return evt;
                            }

                            currentTextBuilder = null;
                            currentMessageBuilder = null;
                            accumulatedText = null;
                        }

                        previousMessageId = update.MessageId;

                        if (currentMessageBuilder is null)
                        {
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

                    case FunctionCallContent funcCall:
                    {
                        foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText))
                        {
                            yield return evt;
                        }

                        currentTextBuilder = null;
                        currentMessageBuilder = null;
                        accumulatedText = null;
                        previousMessageId = null;

                        var callId = funcCall.CallId ?? Guid.NewGuid().ToString("N");
                        var funcBuilder = stream.AddOutputItemFunctionCall(funcCall.Name, callId);
                        yield return funcBuilder.EmitAdded();

                        var arguments = funcCall.Arguments is not null
                            ? JsonSerializer.Serialize(funcCall.Arguments)
                            : "{}";

                        yield return funcBuilder.EmitArgumentsDelta(arguments);
                        yield return funcBuilder.EmitArgumentsDone(arguments);
                        yield return funcBuilder.EmitDone();
                        break;
                    }

                    case TextReasoningContent reasoningContent:
                    {
                        foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText))
                        {
                            yield return evt;
                        }

                        currentTextBuilder = null;
                        currentMessageBuilder = null;
                        accumulatedText = null;
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

                    case UsageContent usageContent when usageContent.Details is not null:
                    {
                        accumulatedUsage = ConvertUsage(usageContent.Details, accumulatedUsage);
                        break;
                    }

                    case ErrorContent errorContent:
                    {
                        foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText))
                        {
                            yield return evt;
                        }

                        currentTextBuilder = null;
                        currentMessageBuilder = null;
                        accumulatedText = null;
                        previousMessageId = null;
                        hasTerminalEvent = true;

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

                    case FunctionResultContent:
                        // Function results are internal to the agent's tool-calling loop
                        // and are not emitted as output items in the response stream.
                        break;

                    default:
                        break;
                }
            }
        }

        // Close any remaining open message
        foreach (var evt in CloseCurrentMessage(currentMessageBuilder, currentTextBuilder, accumulatedText))
        {
            yield return evt;
        }

        if (!hasTerminalEvent)
        {
            yield return stream.EmitCompleted(accumulatedUsage);
        }
    }

    private static IEnumerable<ResponseStreamEvent> CloseCurrentMessage(
        OutputItemMessageBuilder? messageBuilder,
        TextContentBuilder? textBuilder,
        StringBuilder? accumulatedText)
    {
        if (messageBuilder is null)
        {
            yield break;
        }

        if (textBuilder is not null)
        {
            var finalText = accumulatedText?.ToString() ?? string.Empty;
            yield return textBuilder.EmitTextDone(finalText);
            yield return textBuilder.EmitDone();
        }

        yield return messageBuilder.EmitDone();
    }

    private static bool IsSameMessage(string? currentId, string? previousId) =>
        currentId is not { Length: > 0 } || previousId is not { Length: > 0 } || currentId == previousId;

    private static ResponseUsage ConvertUsage(UsageDetails details, ResponseUsage? existing)
    {
        var inputTokens = details.InputTokenCount ?? 0;
        var outputTokens = details.OutputTokenCount ?? 0;
        var totalTokens = details.TotalTokenCount ?? 0;

        var cachedTokens = details.AdditionalCounts?.TryGetValue("InputTokenDetails.CachedTokenCount", out var cached) ?? false
            ? cached : 0;
        var reasoningTokens = details.AdditionalCounts?.TryGetValue("OutputTokenDetails.ReasoningTokenCount", out var reasoning) ?? false
            ? reasoning : 0;

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
}
