// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

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
/// This decorator operates within the context of a running <see cref="AIAgent"/> with an active
/// <see cref="AgentRunContext.Session"/>. When invoked without an ambient run context or session
/// (for example when the chat client is used directly outside of an agent run), the decorator becomes
/// a no-op: it passes the request through to the inner client unchanged, surfacing all approval
/// requests to the caller, and logs a warning.
/// </para>
/// </remarks>
internal sealed partial class ApprovalNotRequiredFunctionBypassingChatClient : DelegatingChatClient
{
    /// <summary>
    /// The key used in <see cref="AgentSessionStateBag"/> to store pending auto-approved function calls
    /// between agent runs.
    /// </summary>
    internal const string StateBagKey = "_autoApprovedFunctionCalls";

    private readonly ILogger _logger;

    private bool _warnedNoSession;

    /// <summary>
    /// Initializes a new instance of the <see cref="ApprovalNotRequiredFunctionBypassingChatClient"/> class.
    /// </summary>
    /// <param name="innerClient">The underlying chat client (typically a <see cref="FunctionInvokingChatClient"/>).</param>
    /// <param name="loggerFactory">An optional <see cref="ILoggerFactory"/> used to create a logger for diagnostics.</param>
    public ApprovalNotRequiredFunctionBypassingChatClient(IChatClient innerClient, ILoggerFactory? loggerFactory = null)
        : base(innerClient)
    {
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<ApprovalNotRequiredFunctionBypassingChatClient>();
    }

    /// <inheritdoc/>
    public override async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        if (!this.TryGetSession(out var session))
        {
            return await base.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false);
        }

        var autoApprovableNames = this.GetAutoApprovableToolNames(options);

        messages = InjectPendingAutoApprovals(messages, session);

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
        if (!this.TryGetSession(out var session))
        {
            await foreach (var passthrough in base.GetStreamingResponseAsync(messages, options, cancellationToken).ConfigureAwait(false))
            {
                yield return passthrough;
            }

            yield break;
        }

        var autoApprovableNames = this.GetAutoApprovableToolNames(options);

        messages = InjectPendingAutoApprovals(messages, session);
        List<ToolApprovalRequestContent>? autoApproved = null;

        try
        {
            await foreach (var update in base.GetStreamingResponseAsync(messages, options, cancellationToken).ConfigureAwait(false))
            {
                if (FilterUpdateContents(update, autoApprovableNames, ref autoApproved))
                {
                    yield return update;
                }
            }
        }
        finally
        {
            if (autoApproved is { Count: > 0 })
            {
                session.StateBag.SetValue(StateBagKey, autoApproved, AgentJsonUtilities.DefaultOptions);
            }
        }
    }

    /// <summary>
    /// Attempts to get the current <see cref="AgentSession"/> from the ambient run context. When no run
    /// context or session is available, logs a warning (once per instance) and returns <see langword="false"/>
    /// so the caller can pass the request through without applying bypassing.
    /// </summary>
    private bool TryGetSession([NotNullWhen(true)] out AgentSession? session)
    {
        session = AIAgent.CurrentRunContext?.Session;

        if (session is null)
        {
            if (!this._warnedNoSession)
            {
                this._warnedNoSession = true;
                LogBypassingSkipped(this._logger);
            }

            return false;
        }

        return true;
    }

    [LoggerMessage(LogLevel.Warning, "ApprovalNotRequiredFunctionBypassingChatClient was invoked without an active agent run context or session. Approval-not-required function bypassing is skipped and all approval requests are surfaced to the caller. Invoke the chat client through AIAgent.RunAsync or AIAgent.RunStreamingAsync to enable bypassing.")]
    private static partial void LogBypassingSkipped(ILogger logger);

    /// <summary>
    /// Checks the session for stored auto-approvals from a previous turn and injects them as
    /// a user message containing <see cref="ToolApprovalResponseContent"/> items appended to the input messages.
    /// </summary>
    /// <remarks>
    /// All stored requests are unconditionally injected as approved responses regardless of whether the
    /// tool set has changed, because the LLM requires a complete set of tool call responses for a prior turn.
    /// </remarks>
    private static IEnumerable<ChatMessage> InjectPendingAutoApprovals(
        IEnumerable<ChatMessage> messages,
        AgentSession session)
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
            approvalResponses.Add(request.CreateResponse(approved: true));
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

        for (int i = messages.Count - 1; i >= 0; i--)
        {
            var message = messages[i];
            bool removedFromMessage = false;

            for (int j = message.Contents.Count - 1; j >= 0; j--)
            {
                if (message.Contents[j] is ToolApprovalRequestContent approval
                    && IsAutoApprovable(approval, autoApprovableNames))
                {
                    (autoApproved ??= []).Add(approval);
                    message.Contents.RemoveAt(j);
                    removedFromMessage = true;
                }
            }

            // Only remove a message that this decorator emptied by stripping auto-approved
            // content. Messages that were already empty (for example metadata-only messages)
            // are left untouched.
            if (removedFromMessage && message.Contents.Count == 0)
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
