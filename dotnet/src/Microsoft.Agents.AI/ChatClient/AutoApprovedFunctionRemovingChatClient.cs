// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// A delegating chat client that automatically removes <see cref="ToolApprovalRequestContent"/> for tools
/// that do not actually require approval, storing auto-approved results in the session for transparent
/// re-injection on the next request.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="FunctionInvokingChatClient"/> has an all-or-nothing behavior for approvals: when any tool
/// in a response is an <see cref="ApprovalRequiredAIFunction"/>, it converts all <see cref="FunctionCallContent"/>
/// items to <see cref="ToolApprovalRequestContent"/> — even for tools that do not require approval. This
/// decorator sits above <see cref="FunctionInvokingChatClient"/> in the pipeline and transparently handles
/// the non-approval-required items so callers only see approval requests for tools that truly need them.
/// </para>
/// <para>
/// On outbound responses, the decorator identifies <see cref="ToolApprovalRequestContent"/> items for tools
/// that are not wrapped in <see cref="ApprovalRequiredAIFunction"/>, removes them from the response, and
/// stores them in the session's <see cref="AgentSessionStateBag"/>. On the next inbound request, the stored
/// items are re-injected as pre-approved <see cref="ToolApprovalResponseContent"/> so that
/// <see cref="FunctionInvokingChatClient"/> can process them alongside the caller's human-approved responses.
/// </para>
/// <para>
/// This decorator requires an active <see cref="AIAgent.CurrentRunContext"/> with a non-null
/// <see cref="AgentRunContext.Session"/>. An <see cref="InvalidOperationException"/> is thrown if no
/// run context or session is available.
/// </para>
/// </remarks>
internal sealed class AutoApprovedFunctionRemovingChatClient : DelegatingChatClient
{
    /// <summary>
    /// The key used in <see cref="AgentSessionStateBag"/> to store pending auto-approved function calls
    /// between agent runs.
    /// </summary>
    internal const string StateBagKey = "_autoApprovedFunctionCalls";

    /// <summary>
    /// Initializes a new instance of the <see cref="AutoApprovedFunctionRemovingChatClient"/> class.
    /// </summary>
    /// <param name="innerClient">The underlying chat client (typically a <see cref="FunctionInvokingChatClient"/>).</param>
    public AutoApprovedFunctionRemovingChatClient(IChatClient innerClient)
        : base(innerClient)
    {
    }

    /// <inheritdoc/>
    public override async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var session = GetRequiredSession();
        var autoApprovableNames = this.GetAutoApprovableToolNames(options);

        messages = InjectPendingAutoApprovals(messages, session, autoApprovableNames);

        var response = await base.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false);

        RemoveAutoApprovedFromMessages(response.Messages, autoApprovableNames, session);

        return response;
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var session = GetRequiredSession();
        var autoApprovableNames = this.GetAutoApprovableToolNames(options);

        messages = InjectPendingAutoApprovals(messages, session, autoApprovableNames);
        List<ToolApprovalRequestContent>? autoApproved = null;

        await foreach (var update in base.GetStreamingResponseAsync(messages, options, cancellationToken).ConfigureAwait(false))
        {
            if (FilterUpdateContents(update, autoApprovableNames, ref autoApproved))
            {
                yield return update;
            }
        }

        if (autoApproved is { Count: > 0 })
        {
            session.StateBag.SetValue(StateBagKey, autoApproved, AgentJsonUtilities.DefaultOptions);
        }
    }

    /// <summary>
    /// Gets the current <see cref="AgentSession"/> from the ambient run context.
    /// </summary>
    /// <exception cref="InvalidOperationException">No run context or session is available.</exception>
    private static AgentSession GetRequiredSession()
    {
        var runContext = AIAgent.CurrentRunContext
            ?? throw new InvalidOperationException(
                $"{nameof(AutoApprovedFunctionRemovingChatClient)} can only be used within the context of a running AIAgent. " +
                "Ensure that the chat client is being invoked as part of an AIAgent.RunAsync or AIAgent.RunStreamingAsync call.");

        return runContext.Session
            ?? throw new InvalidOperationException(
                $"{nameof(AutoApprovedFunctionRemovingChatClient)} requires a session. " +
                "Ensure the agent has a resolved session before invoking the chat client.");
    }

    /// <summary>
    /// Checks the session for stored auto-approvals from a previous turn and injects them as
    /// a user message containing <see cref="ToolApprovalResponseContent"/> items appended to the input messages.
    /// </summary>
    private static IEnumerable<ChatMessage> InjectPendingAutoApprovals(
        IEnumerable<ChatMessage> messages,
        AgentSession session,
        HashSet<string> autoApprovableNames)
    {
        if (!session.StateBag.TryGetValue<List<ToolApprovalRequestContent>>(
            StateBagKey,
            out var pendingRequests,
            AgentJsonUtilities.DefaultOptions)
            || pendingRequests is not { Count: > 0 })
        {
            return messages;
        }

        session.StateBag.TryRemoveValue(StateBagKey);

        List<AIContent> approvalResponses = [];
        foreach (var request in pendingRequests)
        {
            if (IsAutoApprovable(request, autoApprovableNames))
            {
                approvalResponses.Add(request.CreateResponse(approved: true));
            }
        }

        if (approvalResponses.Count == 0)
        {
            return messages;
        }

        var userMessage = new ChatMessage(ChatRole.User, approvalResponses);
        return messages.Concat([userMessage]);
    }

    /// <summary>
    /// Builds a set of tool names that do not require approval and can be auto-approved,
    /// by checking all available tools from <see cref="ChatOptions.Tools"/> and
    /// <see cref="FunctionInvokingChatClient.AdditionalTools"/>.
    /// </summary>
    private HashSet<string> GetAutoApprovableToolNames(ChatOptions? options)
    {
        var ficc = this.GetService<FunctionInvokingChatClient>();

        var allTools = (options?.Tools ?? Enumerable.Empty<AITool>())
            .Concat(ficc?.AdditionalTools ?? Enumerable.Empty<AITool>());

        return new HashSet<string>(
            allTools
                .OfType<AIFunction>()
                .Where(static f => f.GetService<ApprovalRequiredAIFunction>() is null)
                .Select(static f => f.Name),
            StringComparer.Ordinal);
    }

    /// <summary>
    /// Determines whether a <see cref="ToolApprovalRequestContent"/> can be auto-approved because
    /// the underlying tool is not an <see cref="ApprovalRequiredAIFunction"/>.
    /// </summary>
    /// <returns>
    /// <see langword="true"/> if the approval request is for a known tool that does not require approval
    /// and can be auto-approved; <see langword="false"/> otherwise.
    /// </returns>
    private static bool IsAutoApprovable(ToolApprovalRequestContent approval, HashSet<string> autoApprovableNames)
    {
        if (approval.ToolCall is not FunctionCallContent fcc)
        {
            // Non-function tool calls cannot be auto-approved.
            return false;
        }

        // Auto-approve only if the tool is known and explicitly does NOT require approval.
        // Unknown tools are not in the set and are treated as approval-required (safe default).
        return autoApprovableNames.Contains(fcc.Name);
    }

    /// <summary>
    /// Scans response messages for auto-approvable <see cref="ToolApprovalRequestContent"/> items,
    /// removes them from the messages, and stores them in the session for the next request.
    /// </summary>
    private static void RemoveAutoApprovedFromMessages(
        IList<ChatMessage> messages,
        HashSet<string> autoApprovableNames,
        AgentSession session)
    {
        List<ToolApprovalRequestContent>? autoApproved = null;

        foreach (var message in messages)
        {
            for (int i = message.Contents.Count - 1; i >= 0; i--)
            {
                if (message.Contents[i] is ToolApprovalRequestContent approval
                    && IsAutoApprovable(approval, autoApprovableNames))
                {
                    (autoApproved ??= []).Add(approval);
                    message.Contents.RemoveAt(i);
                }
            }
        }

        // Remove messages that are now empty after filtering.
        for (int i = messages.Count - 1; i >= 0; i--)
        {
            if (messages[i].Contents.Count == 0)
            {
                messages.RemoveAt(i);
            }
        }

        if (autoApproved is { Count: > 0 })
        {
            session.StateBag.SetValue(StateBagKey, autoApproved, AgentJsonUtilities.DefaultOptions);
        }
    }

    /// <summary>
    /// Filters auto-approvable <see cref="ToolApprovalRequestContent"/> items from a streaming update's
    /// contents, collecting them for later storage.
    /// </summary>
    /// <returns>
    /// <see langword="true"/> if the update should be yielded (has remaining content or had no
    /// approval content to begin with); <see langword="false"/> if the update is now empty and
    /// should be skipped.
    /// </returns>
    private static bool FilterUpdateContents(
        ChatResponseUpdate update,
        HashSet<string> autoApprovableNames,
        ref List<ToolApprovalRequestContent>? autoApproved)
    {
        bool hasApprovalContent = false;
        List<AIContent> filteredContents = [];
        bool removedAny = false;

        for (int i = 0; i < update.Contents.Count; i++)
        {
            var content = update.Contents[i];

            if (content is ToolApprovalRequestContent approval)
            {
                hasApprovalContent = true;

                if (IsAutoApprovable(approval, autoApprovableNames))
                {
                    (autoApproved ??= []).Add(approval);
                    removedAny = true;
                }
                else
                {
                    filteredContents.Add(content);
                }
            }
            else
            {
                filteredContents.Add(content);
            }
        }

        if (removedAny)
        {
            update.Contents = filteredContents;
        }

        // Yield the update unless it was purely auto-approvable approval content (now empty).
        return update.Contents.Count > 0 || !hasApprovalContent;
    }
}
