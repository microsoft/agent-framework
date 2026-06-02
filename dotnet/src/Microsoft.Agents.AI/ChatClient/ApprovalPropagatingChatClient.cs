// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.ChatClient;

/// <summary>
/// Propagates nested tool approval requests attached to function calls back through the chat response.
/// </summary>
internal sealed class ApprovalPropagatingChatClient : DelegatingChatClient
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ApprovalPropagatingChatClient"/> class.
    /// </summary>
    /// <param name="innerClient">The inner chat client.</param>
    public ApprovalPropagatingChatClient(IChatClient innerClient)
        : base(innerClient)
    {
    }

    /// <inheritdoc />
    public override async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var response = await base.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false);
        List<ChatMessage>? approvalMessages = null;
        HashSet<string>? pendingApprovalCallIds = null;

        foreach (var message in response.Messages)
        {
            foreach (var functionCall in message.Contents.OfType<FunctionCallContent>())
            {
                var approvals = ToolApprovalRequestPropagator.TakeApprovals(functionCall);
                if (approvals is not null)
                {
                    approvalMessages ??= [];
                    pendingApprovalCallIds ??= [];
                    pendingApprovalCallIds.Add(functionCall.CallId);
                    approvalMessages.Add(new ChatMessage(ChatRole.Assistant, [.. approvals]));
                }
            }
        }

        if (approvalMessages is not null)
        {
            RemoveFunctionResults(response.Messages, pendingApprovalCallIds!);

            foreach (var approvalMessage in approvalMessages)
            {
                response.Messages.Add(approvalMessage);
            }
        }

        return response;
    }

    /// <inheritdoc />
    public override async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        List<ToolApprovalRequestContent>? approvalsToPropagate = null;
        HashSet<string>? pendingApprovalCallIds = null;

        await foreach (var update in base.GetStreamingResponseAsync(messages, options, cancellationToken).ConfigureAwait(false))
        {
            foreach (var functionCall in update.Contents.OfType<FunctionCallContent>())
            {
                var approvals = ToolApprovalRequestPropagator.TakeApprovals(functionCall);
                if (approvals is not null)
                {
                    approvalsToPropagate ??= [];
                    pendingApprovalCallIds ??= [];
                    pendingApprovalCallIds.Add(functionCall.CallId);
                    approvalsToPropagate.AddRange(approvals);
                }
            }

            var filteredUpdate = pendingApprovalCallIds is null ? update : RemoveFunctionResults(update, pendingApprovalCallIds);
            if (filteredUpdate.Contents.Count > 0)
            {
                yield return filteredUpdate;
            }
        }

        if (approvalsToPropagate is not null)
        {
            yield return new ChatResponseUpdate(ChatRole.Assistant, [.. approvalsToPropagate]);
        }
    }

    private static ChatResponseUpdate RemoveFunctionResults(ChatResponseUpdate update, HashSet<string> callIds)
    {
        if (!update.Contents.OfType<FunctionResultContent>().Any(result => callIds.Contains(result.CallId)))
        {
            return update;
        }

        return new ChatResponseUpdate(update.Role, update.Contents
            .Where(content => content is not FunctionResultContent result || !callIds.Contains(result.CallId))
            .ToList())
        {
            AdditionalProperties = update.AdditionalProperties,
            AuthorName = update.AuthorName,
            ConversationId = update.ConversationId,
            CreatedAt = update.CreatedAt,
            FinishReason = update.FinishReason,
            MessageId = update.MessageId,
            RawRepresentation = update.RawRepresentation,
            ResponseId = update.ResponseId,
        };
    }

    private static void RemoveFunctionResults(IList<ChatMessage> messages, HashSet<string> callIds)
    {
        for (int i = messages.Count - 1; i >= 0; i--)
        {
            var message = messages[i];
            if (!message.Contents.OfType<FunctionResultContent>().Any(result => callIds.Contains(result.CallId)))
            {
                continue;
            }

            var remainingContents = message.Contents
                .Where(content => content is not FunctionResultContent result || !callIds.Contains(result.CallId))
                .ToList();

            if (remainingContents.Count == 0)
            {
                messages.RemoveAt(i);
            }
            else
            {
                var clonedMessage = message.Clone();
                clonedMessage.Contents = remainingContents;
                messages[i] = clonedMessage;
            }
        }
    }
}
