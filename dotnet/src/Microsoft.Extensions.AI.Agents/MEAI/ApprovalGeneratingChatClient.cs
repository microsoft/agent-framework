// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents a chat client that seeks user approval for function calls.
/// </summary>
public class ApprovalGeneratingChatClient : DelegatingChatClient
{
    /// <summary>The logger to use for logging information about function approval.</summary>
    private readonly ILogger _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="ApprovalGeneratingChatClient"/> class.
    /// </summary>
    /// <param name="innerClient">The underlying <see cref="IChatClient"/>, or the next instance in a chain of clients.</param>
    /// <param name="loggerFactory">An <see cref="ILoggerFactory"/> to use for logging information about function invocation.</param>
    public ApprovalGeneratingChatClient(IChatClient innerClient, ILoggerFactory? loggerFactory = null)
        : base(innerClient)
    {
        this._logger = (ILogger?)loggerFactory?.CreateLogger<ApprovalGeneratingChatClient>() ?? NullLogger.Instance;
    }

    /// <inheritdoc />
    public override async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        var messagesList = messages as IList<ChatMessage> ?? messages.ToList();

        // If we got any approval responses, and we also got FunctionResultContent for those approvals, we can filter out those approval responses
        // since they are already handled.
        RemoveExecutedApprovedApprovalRequests(messagesList);

        // Get all the remaining approval responses.
        var approvalResponses = messagesList.SelectMany(x => x.Contents).OfType<FunctionApprovalResponseContent>().ToList();

        if (approvalResponses.Count == 0)
        {
            // We have no approval responses, so we can just call the inner client.
            var response = await base.GetResponseAsync(messagesList, options, cancellationToken).ConfigureAwait(false);
            if (response is null)
            {
                Throw.InvalidOperationException($"The inner {nameof(IChatClient)} returned a null {nameof(ChatResponse)}.");
            }

            // Replace any FunctionCallContent in the response with FunctionApprovalRequestContent.
            ReplaceFunctionCallsWithApprovalRequests(response.Messages);

            return response;
        }

        if (approvalResponses.All(x => !x.Approved))
        {
            // If we only have rejections, we can call the inner client with rejected function calls.
            // Replace all rejected FunctionApprovalResponseContent with rejected FunctionResultContent.
            ReplaceRejectedFunctionCallRequests(messagesList);

            var response = await base.GetResponseAsync(messagesList, options, cancellationToken).ConfigureAwait(false);
            if (response is null)
            {
                Throw.InvalidOperationException($"The inner {nameof(IChatClient)} returned a null {nameof(ChatResponse)}.");
            }

            // Replace any FunctionCallContent in the response with FunctionApprovalRequestContent.
            ReplaceFunctionCallsWithApprovalRequests(response.Messages);

            return response;
        }

        // We have a mix of approvals and rejections, so we need to return the approved function calls
        // to the upper layer for invocation.
        // We do nothing with the rejected ones. They must be supplied by the caller again
        // on the next invocation, and then we will convert them to rejected FunctionResultContent.
        var approvedToolCalls = approvalResponses.Where(x => x.Approved).Select(x => x.FunctionCall).Cast<AIContent>().ToList();
        return new ChatResponse
        {
            ConversationId = options?.ConversationId,
            CreatedAt = DateTimeOffset.UtcNow,
            FinishReason = ChatFinishReason.ToolCalls,
            ResponseId = Guid.NewGuid().ToString(),
            Messages =
            [
                new ChatMessage(ChatRole.Assistant, approvedToolCalls)
            ]
        };
    }

    /// <inheritdoc />
    public override IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        return base.GetStreamingResponseAsync(messages, options, cancellationToken);
    }

    private static void RemoveExecutedApprovedApprovalRequests(IList<ChatMessage> messages)
    {
        var functionResultCallIds = messages.SelectMany(x => x.Contents).OfType<FunctionResultContent>().Select(x => x.CallId).ToHashSet();

        int messageCount = messages.Count;
        for (int i = 0; i < messageCount; i++)
        {
            // Get any content that is not a FunctionApprovalResponseContent or is a FunctionApprovalResponseContent that has not been executed.
            var content = messages[i].Contents.Where(x => x is not FunctionApprovalResponseContent || (x is FunctionApprovalResponseContent approval && !functionResultCallIds.Contains(approval.FunctionCall.CallId))).ToList();

            // Remove the entire message if there is no content left after filtering.
            if (content.Count == 0)
            {
                messages.RemoveAt(i);
                i--; // Adjust index since we removed an item.
                messageCount--; // Adjust count since we removed an item.
                continue;
            }

            // Replace the message contents with the filtered content.
            messages[i].Contents = content;
        }
    }

    private static void ReplaceRejectedFunctionCallRequests(IList<ChatMessage> messages)
    {
        List<ChatMessage> newMessages = [];

        int messageCount = messages.Count;
        for (int i = 0; i < messageCount; i++)
        {
            var content = messages[i].Contents;

            List<AIContent> replacedContent = [];
            List<AIContent> toolCalls = [];
            int contentCount = content.Count;
            for (int j = 0; j < contentCount; j++)
            {
                // Find all responses that were rejected, and replace them with a FunctionResultContent indicating the rejection.
                if (content[j] is FunctionApprovalResponseContent approval && !approval.Approved)
                {
                    var rejectedFunctionCall = new FunctionResultContent(approval.FunctionCall.CallId, "Error: Function invocation approval was not granted.");
                    replacedContent.Add(rejectedFunctionCall);
                    content[j] = rejectedFunctionCall;
                    toolCalls.Add(approval.FunctionCall);
                }
            }

            // Since approvals are submitted as part of a user messages, we have to move the
            // replaced function results to tool messages.
            if (replacedContent.Count == contentCount)
            {
                // If all content was replaced, we can replace the entire message with a new tool message.
                messages.RemoveAt(i);
                i--; // Adjust index since we removed an item.
                messageCount--; // Adjust count since we removed an item.

                newMessages.Add(new ChatMessage(ChatRole.Assistant, toolCalls));
                newMessages.Add(new ChatMessage(ChatRole.Tool, replacedContent));
            }
            else if (replacedContent.Count > 0)
            {
                // If only some content was replaced, we move the updated content to a new tool message.
                foreach (var replacedItem in replacedContent)
                {
                    messages[i].Contents.Remove(replacedItem);
                }

                newMessages.Add(new ChatMessage(ChatRole.Assistant, toolCalls));
                newMessages.Add(new ChatMessage(ChatRole.Tool, replacedContent));
            }
        }

        if (newMessages.Count > 0)
        {
            // If we have new messages, we add them to the original messages.
            foreach (var newMessage in newMessages)
            {
                messages.Add(newMessage);
            }
        }
    }

    /// <summary>Replaces any <see cref="FunctionCallContent"/> from <paramref name="messages"/> with <see cref="FunctionApprovalRequestContent"/>.</summary>
    private static void ReplaceFunctionCallsWithApprovalRequests(IList<ChatMessage> messages)
    {
        int count = messages.Count;
        for (int i = 0; i < count; i++)
        {
            ReplaceFunctionCallsWithApprovalRequests(messages[i].Contents);
        }
    }

    /// <summary>Copies any <see cref="FunctionCallContent"/> from <paramref name="content"/> with <see cref="FunctionApprovalRequestContent"/>.</summary>
    private static void ReplaceFunctionCallsWithApprovalRequests(IList<AIContent> content)
    {
        int count = content.Count;
        for (int i = 0; i < count; i++)
        {
            if (content[i] is FunctionCallContent functionCall)
            {
                content[i] = new FunctionApprovalRequestContent
                {
                    FunctionCall = functionCall,
                    ApprovalId = functionCall.CallId
                };
            }
        }
    }
}
