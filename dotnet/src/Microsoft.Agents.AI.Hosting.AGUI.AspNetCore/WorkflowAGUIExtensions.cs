// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using AGUI.Abstractions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

internal static class WorkflowAGUIExtensions
{
#pragma warning disable VSTHRD200 // The name describes a stream transformation, consistent with the requested pipeline.
    internal static async IAsyncEnumerable<ChatResponseUpdate> MapWorkflowEventsToAGUI(
        this IAsyncEnumerable<ChatResponseUpdate> updates)
    {
        ArgumentNullException.ThrowIfNull(updates);
        List<ChatResponseUpdate> interruptions = [];
        List<ChatResponseUpdate> uncorrelatedApprovalRequests = [];

        await foreach (ChatResponseUpdate update in updates.ConfigureAwait(false))
        {
            switch (update.RawRepresentation)
            {
                case AgentResponseUpdate { RawRepresentation: RequestInfoEvent }
                    when update.Contents.OfType<ToolApprovalRequestContent>().SingleOrDefault() is { } approvalRequest:
                    uncorrelatedApprovalRequests.RemoveAll(candidate =>
                        candidate.Contents.OfType<ToolApprovalRequestContent>().Any(candidateRequest =>
                            candidateRequest.ToolCall.CallId == approvalRequest.ToolCall.CallId));
                    yield return update;
                    break;

                case AgentResponseUpdate { RawRepresentation: RequestInfoEvent requestInfo }
                    when update.Contents.OfType<FunctionCallContent>().SingleOrDefault() is { } request:
                    update.Contents =
                    [
                        new InterruptRequestContent(requestInfo.Request.RequestId)
                        {
                            Message = $"Input required for {request.Name}.",
                            Reason = InterruptReasons.InputRequired,
                            ToolCallId = request.CallId,
                        },
                    ];
                    update.RawRepresentation = null;
                    interruptions.Add(update);
                    break;

                case AgentResponseUpdate { RawRepresentation: ExecutorInvokedEvent invoked }:
                    update.RawRepresentation = new StepStartedEvent { StepName = invoked.ExecutorId };
                    yield return update;
                    break;

                case AgentResponseUpdate { RawRepresentation: ExecutorCompletedEvent completed }:
                    update.RawRepresentation = new StepFinishedEvent { StepName = completed.ExecutorId };
                    yield return update;
                    break;

                case AgentResponseUpdate { RawRepresentation: ExecutorFailedEvent failed }:
                    yield return CreateEventUpdate(
                        update,
                        new StepFinishedEvent { StepName = failed.ExecutorId },
                        includeContents: false);
                    yield return CreateEventUpdate(
                        update,
                        new RunErrorEvent
                        {
                            Message = update.Contents.OfType<ErrorContent>().SingleOrDefault()?.Message
                                ?? "An error occurred while executing the workflow.",
                        },
                        includeContents: false);
                    break;

                case var _ when update.Contents.OfType<ToolApprovalRequestContent>().Any():
                    uncorrelatedApprovalRequests.Add(update);
                    break;

                default:
                    yield return update;
                    break;
            }
        }

        foreach (ChatResponseUpdate interruption in interruptions)
        {
            yield return interruption;
        }

        foreach (ChatResponseUpdate approvalRequest in uncorrelatedApprovalRequests)
        {
            yield return approvalRequest;
        }
    }
#pragma warning restore VSTHRD200

    // TODO: Remove this adapter after consuming an AG-UI .NET release containing
    // https://github.com/ag-ui-protocol/ag-ui/pull/2455, which makes RUN_ERROR terminal
    // and prevents the SDK from appending RUN_FINISHED(success).
    internal static async IAsyncEnumerable<BaseEvent> MakeRunErrorTerminalAsync(
        this IAsyncEnumerable<BaseEvent> events)
    {
        ArgumentNullException.ThrowIfNull(events);
        RunErrorEvent? runError = null;
        List<string> activeSteps = [];
        List<string> activeTextMessages = [];
        List<string> activeToolCalls = [];
        List<string> activeReasoning = [];
        List<string> activeReasoningMessages = [];

        await foreach (BaseEvent evt in events.ConfigureAwait(false))
        {
            if (runError is null)
            {
                if (evt is RunErrorEvent error)
                {
                    runError = error;
                }
                else
                {
                    TrackLifecycle(evt);
                    yield return evt;
                }
            }
            else if (IsMatchingClosure(evt))
            {
                yield return evt;
            }
        }

        if (runError is not null)
        {
            foreach (string toolCallId in activeToolCalls)
            {
                yield return new ToolCallEndEvent { ToolCallId = toolCallId };
            }

            foreach (string messageId in activeTextMessages)
            {
                yield return new TextMessageEndEvent { MessageId = messageId };
            }

            foreach (string messageId in activeReasoningMessages)
            {
                yield return new ReasoningMessageEndEvent { MessageId = messageId };
            }

            foreach (string messageId in activeReasoning)
            {
                yield return new ReasoningEndEvent { MessageId = messageId };
            }

            foreach (string stepName in activeSteps)
            {
                yield return new StepFinishedEvent { StepName = stepName };
            }

            yield return runError;
        }

        void TrackLifecycle(BaseEvent evt)
        {
            switch (evt)
            {
                case StepStartedEvent started:
                    Add(activeSteps, started.StepName);
                    break;
                case StepFinishedEvent finished:
                    activeSteps.Remove(finished.StepName);
                    break;
                case TextMessageStartEvent started:
                    Add(activeTextMessages, started.MessageId);
                    break;
                case TextMessageEndEvent finished:
                    activeTextMessages.Remove(finished.MessageId);
                    break;
                case ToolCallStartEvent started:
                    Add(activeToolCalls, started.ToolCallId);
                    break;
                case ToolCallEndEvent finished:
                    activeToolCalls.Remove(finished.ToolCallId);
                    break;
                case ReasoningStartEvent started:
                    Add(activeReasoning, started.MessageId);
                    break;
                case ReasoningEndEvent finished:
                    activeReasoning.Remove(finished.MessageId);
                    break;
                case ReasoningMessageStartEvent started:
                    Add(activeReasoningMessages, started.MessageId);
                    break;
                case ReasoningMessageEndEvent finished:
                    activeReasoningMessages.Remove(finished.MessageId);
                    break;
            }
        }

        bool IsMatchingClosure(BaseEvent evt)
            => evt switch
            {
                StepFinishedEvent finished => activeSteps.Remove(finished.StepName),
                TextMessageEndEvent finished => activeTextMessages.Remove(finished.MessageId),
                ToolCallEndEvent finished => activeToolCalls.Remove(finished.ToolCallId),
                ReasoningEndEvent finished => activeReasoning.Remove(finished.MessageId),
                ReasoningMessageEndEvent finished => activeReasoningMessages.Remove(finished.MessageId),
                _ => false,
            };

        static void Add(List<string> activeItems, string id)
        {
            if (!activeItems.Contains(id, StringComparer.Ordinal))
            {
                activeItems.Add(id);
            }
        }
    }

    private static ChatResponseUpdate CreateEventUpdate(
        ChatResponseUpdate update,
        BaseEvent evt,
        bool includeContents = true)
        => new()
        {
            AdditionalProperties = update.AdditionalProperties,
            AuthorName = update.AuthorName,
            Contents = includeContents ? update.Contents : [],
            CreatedAt = update.CreatedAt,
            FinishReason = update.FinishReason,
            MessageId = update.MessageId,
            RawRepresentation = evt,
            ResponseId = update.ResponseId,
            Role = update.Role,
            ContinuationToken = update.ContinuationToken,
        };

    internal static List<ChatMessage> MapAGUIInterruptResponsesToFunctionResults(
        this IEnumerable<ChatMessage> messages)
        => [.. messages.Select(static message =>
        {
            AIContent[] contents = [.. message.Contents.Select(static content =>
                content is InterruptResponseContent response
                    ? new FunctionResultContent(response.RequestId, response.Payload)
                    : content)];

            return new ChatMessage(message.Role, contents)
            {
                AdditionalProperties = message.AdditionalProperties,
                AuthorName = message.AuthorName,
                CreatedAt = message.CreatedAt,
                MessageId = message.MessageId,
                RawRepresentation = message.RawRepresentation,
            };
        })];
}
