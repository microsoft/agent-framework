// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Shared helpers for copying tool-approval requests and ordering approval responses in chat messages.
/// </summary>
internal static class ToolApprovalHelpers
{
    /// <summary>
    /// Creates a new <see cref="ToolApprovalRequestContent"/> and <see cref="FunctionCallContent"/> with the
    /// original request id, call id, function name, arguments, and metadata. The copied function call has
    /// <see cref="FunctionCallContent.InformationalOnly"/> set to <see langword="false"/> so a recorded pending
    /// request remains executable on retry. Returns requests for other tool-call types unchanged.
    /// </summary>
    internal static ToolApprovalRequestContent SnapshotRequest(ToolApprovalRequestContent request)
    {
        if (request.ToolCall is FunctionCallContent functionCall)
        {
            var clonedCall = new FunctionCallContent(
                functionCall.CallId,
                functionCall.Name,
                functionCall.Arguments is null ? null : new Dictionary<string, object?>(functionCall.Arguments))
            {
                AdditionalProperties = functionCall.AdditionalProperties is null ? null : new(functionCall.AdditionalProperties),
                RawRepresentation = functionCall.RawRepresentation,
                Annotations = functionCall.Annotations is null ? null : new List<AIAnnotation>(functionCall.Annotations),
            };

            return new ToolApprovalRequestContent(request.RequestId, clonedCall)
            {
                AdditionalProperties = request.AdditionalProperties is null ? null : new(request.AdditionalProperties),
                RawRepresentation = request.RawRepresentation,
                Annotations = request.Annotations is null ? null : new List<AIAnnotation>(request.Annotations),
            };
        }

        return request;
    }

    /// <summary>
    /// Groups <see cref="ToolApprovalResponseContent"/> items whose function calls have
    /// <see cref="FunctionCallContent.InformationalOnly"/> set to <see langword="false"/> after the input's
    /// approval requests and before new caller messages. If no such request is present, responses follow
    /// messages tagged as chat history, or precede all messages if none are tagged.
    /// Both approval decorators use this because <see cref="FunctionInvokingChatClient"/> inserts tool results
    /// at the last approval message; an automatic response appended after a new question would put the
    /// tool results after that question.
    /// </summary>
    /// <remarks>
    /// Returns the original list when there are no function-approval responses to move or add.
    /// Other input sequences are materialized once.
    /// </remarks>
    internal static List<ChatMessage> PrepareApprovalMessages(
        IEnumerable<ChatMessage> messages, List<AIContent>? additionalResponses)
    {
        List<ChatMessage> messageList = messages as List<ChatMessage> ?? new List<ChatMessage>(messages);
        List<ChatMessage>? result = null;
        List<ChatMessage>? decisions = null;
        int insertIndex = 0;
        bool foundRequest = false;

        for (int i = 0; i < messageList.Count; i++)
        {
            var message = messageList[i];
            List<AIContent>? responses = null;
            List<AIContent>? remaining = null;
            bool hasRequest = false;
            for (int j = 0; j < message.Contents.Count; j++)
            {
                var content = message.Contents[j];
                if (content is ToolApprovalResponseContent { ToolCall: FunctionCallContent { InformationalOnly: false } })
                {
                    if (responses is null)
                    {
                        responses = [];
                        remaining = new List<AIContent>(message.Contents.Count);
                        for (int k = 0; k < j; k++)
                        {
                            remaining.Add(message.Contents[k]);
                        }
                    }

                    responses.Add(content);
                }
                else
                {
                    remaining?.Add(content);
                    hasRequest |= content is ToolApprovalRequestContent { ToolCall: FunctionCallContent { InformationalOnly: false } };
                }
            }

            if (responses is null)
            {
                result?.Add(message);
            }
            else
            {
                if (result is null)
                {
                    result = new List<ChatMessage>(messageList.Count);
                    for (int k = 0; k < i; k++)
                    {
                        result.Add(messageList[k]);
                    }
                }

                var decisionMessage = message.Clone();
                decisionMessage.Contents = responses;
                (decisions ??= []).Add(decisionMessage);
                if (remaining is { Count: > 0 })
                {
                    var remainingMessage = message.Clone();
                    remainingMessage.Contents = remaining;
                    result.Add(remainingMessage);
                }
            }

            if (hasRequest)
            {
                foundRequest = true;
                insertIndex = result?.Count ?? i + 1;
            }
            else if (!foundRequest && message.GetAgentRequestMessageSourceType() == AgentRequestMessageSourceType.ChatHistory)
            {
                insertIndex = result?.Count ?? i + 1;
            }
        }

        if (additionalResponses is { Count: > 0 })
        {
            (decisions ??= []).Add(new ChatMessage(ChatRole.User, additionalResponses));
        }

        if (decisions is null)
        {
            return messageList;
        }

        result ??= new List<ChatMessage>(messageList);
        result.InsertRange(insertIndex, decisions);
        return result;
    }
}
