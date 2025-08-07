// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents a chat client that seeks user approval for function calls and sits before the <see cref="FunctionInvokingChatClient"/>.
/// </summary>
public class PreFICCApprovalGeneratingChatClient : DelegatingChatClient
{
    /// <summary>The logger to use for logging information about function approval.</summary>
    private readonly ILogger _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="PreFICCApprovalGeneratingChatClient"/> class.
    /// </summary>
    /// <param name="innerClient">The underlying <see cref="IChatClient"/>, or the next instance in a chain of clients.</param>
    /// <param name="loggerFactory">An <see cref="ILoggerFactory"/> to use for logging information about function invocation.</param>
    public PreFICCApprovalGeneratingChatClient(IChatClient innerClient, ILoggerFactory? loggerFactory = null)
        : base(innerClient)
    {
        this._logger = (ILogger?)loggerFactory?.CreateLogger<PreFICCApprovalGeneratingChatClient>() ?? NullLogger.Instance;
    }

    /// <inheritdoc />
    public override async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        var messagesList = messages as IList<ChatMessage> ?? messages.ToList();

        // If we got any FunctionApprovalResponseContent, we can remove the FunctionApprovalRequestContent for those responses, since the FunctionApprovalResponseContent
        // will be turned into FunctionCallContent and FunctionResultContent later, but the FunctionApprovalRequestContent is now unecessary.
        // If we got any approval request/responses, and we also already have FunctionResultContent for those, we can filter out those requests/responses too
        // since they are already handled.
        // This is since the downstream service, may not know what to do with the FunctionApprovalRequestContent/FunctionApprovalResponseContent.
        RemoveExecutedApprovedApprovalRequests(messagesList);

        // Get all the remaining approval responses.
        var approvalResponses = messagesList.SelectMany(x => x.Contents).OfType<FunctionApprovalResponseContent>().ToList();

        // If we have any functions in options, we should clone them and mark any that do not yet have an approval as not invocable.
        options = MakeFunctionsNonInvocable(options, approvalResponses);

        // For rejections we need to replace them with function call content plus rejected function result content.
        // For approvals we need to replace them just with function call content, since the inner client will invoke them.
        ReplaceApprovalResponses(messagesList);

        var response = await base.GetResponseAsync(messagesList, options, cancellationToken).ConfigureAwait(false);
        if (response is null)
        {
            Throw.InvalidOperationException($"The inner {nameof(IChatClient)} returned a null {nameof(ChatResponse)}.");
        }

        // Replace any FunctionCallContent in the response with FunctionApprovalRequestContent.
        ReplaceFunctionCallsWithApprovalRequests(response.Messages);

        return response;
    }

    /// <inheritdoc />
    public override IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        return base.GetStreamingResponseAsync(messages, options, cancellationToken);
    }

    private static void RemoveExecutedApprovedApprovalRequests(IList<ChatMessage> messages)
    {
        var functionResultCallIds = messages.SelectMany(x => x.Contents).OfType<FunctionResultContent>().Select(x => x.CallId).ToHashSet();
        var approvalResponsetIds = messages.SelectMany(x => x.Contents).OfType<FunctionApprovalResponseContent>().Select(x => x.ApprovalId).ToHashSet();

        int messageCount = messages.Count;
        for (int i = 0; i < messageCount; i++)
        {
            // Get any content that is not a FunctionApprovalRequestContent/FunctionApprovalResponseContent or is a FunctionApprovalRequestContent/FunctionApprovalResponseContent that has not been executed.
            var content = messages[i].Contents.Where(x =>
                (x is not FunctionApprovalRequestContent && x is not FunctionApprovalResponseContent) ||
                (x is FunctionApprovalRequestContent request && !approvalResponsetIds.Contains(request.ApprovalId) && !functionResultCallIds.Contains(request.FunctionCall.CallId)) ||
                (x is FunctionApprovalResponseContent approval && !functionResultCallIds.Contains(approval.FunctionCall.CallId))).ToList();

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

    private static void ReplaceApprovalResponses(IList<ChatMessage> messages)
    {
        List<AIContent> approvedFunctionCallContent = [];

        List<AIContent> rejectedFunctionCallContent = [];
        List<AIContent> rejectedFunctionResultContent = [];

        int messageCount = messages.Count;
        for (int i = 0; i < messageCount; i++)
        {
            var content = messages[i].Contents;

            int contentCount = content.Count;

            // ApprovalResponses are submitted as part of a user messages, but FunctionCallContent should be in an assistant message and
            // FunctionResultContent should be in a tool message, so we need to remove them from the user messages, and add them to the appropriate
            // mesages types later.
            for (int j = 0; j < contentCount; j++)
            {
                // Find all responses that were approved, and add the FunctionCallContent for them to the list to add back later.
                if (content[j] is FunctionApprovalResponseContent approval && approval.Approved)
                {
                    content.RemoveAt(j);
                    j--; // Adjust index since we removed an item.
                    contentCount--; // Adjust count since we removed an item.

                    approvedFunctionCallContent.Add(approval.FunctionCall);
                    continue;
                }

                // Find all responses that were rejected, and add their FunctionCallContent and a FunctionResultContent indicating the rejection, to the lists to add back later.
                if (content[j] is FunctionApprovalResponseContent rejection && !rejection.Approved)
                {
                    content.RemoveAt(j);
                    j--; // Adjust index since we removed an item.
                    contentCount--; // Adjust count since we removed an item.

                    var rejectedFunctionCall = new FunctionResultContent(rejection.FunctionCall.CallId, "Error: Function invocation approval was not granted.");
                    rejectedFunctionCallContent.Add(rejection.FunctionCall);
                    rejectedFunctionResultContent.Add(rejectedFunctionCall);
                }
            }

            // If we have no content left in the message after replacing, we can remove the message from the list.
            if (content.Count == 0)
            {
                messages.RemoveAt(i);
                i--; // Adjust index since we removed an item.
                messageCount--; // Adjust count since we removed an item.
            }
        }

        if (rejectedFunctionCallContent.Count > 0)
        {
            messages.Add(new ChatMessage(ChatRole.Assistant, rejectedFunctionCallContent));
            messages.Add(new ChatMessage(ChatRole.Tool, rejectedFunctionResultContent));
        }

        if (approvedFunctionCallContent.Count != 0)
        {
            messages.Add(new ChatMessage(ChatRole.Assistant, approvedFunctionCallContent));
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

    private static ChatOptions? MakeFunctionsNonInvocable(ChatOptions? options, List<FunctionApprovalResponseContent> approvals)
    {
        if (options?.Tools?.Count is > 0)
        {
            options = options.Clone();
            options.Tools = options.Tools!.Select(x =>
            {
                if (x is AIFunction function && !approvals.Any(y => y.FunctionCall.Name == function.Name))
                {
                    var f = new NonInvocableAIFunction(function);
                    return f;
                }
                return x;
            }).ToList();
        }

        return options;
    }
}
