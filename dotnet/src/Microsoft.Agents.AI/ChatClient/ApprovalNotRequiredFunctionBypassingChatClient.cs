// Copyright (c) Microsoft. All rights reserved.

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
/// A stored decision is only reused while the tool it refers to still does not require approval. Before
/// re-injecting, each stored item is re-checked against the tools available to the current turn. If the name
/// has since become approval-required, or has left the tool set, the stored decision is discarded and the call
/// is injected as rejected rather than approved, so that it is not executed. The decision recorded here was the
/// framework's to make only while no approval was needed; once the application asks for a human, a decision
/// taken before that cannot stand in for one.
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

        var autoApprovableNames = ApprovalRequirement.GetApprovalNotRequiredToolNames(this, options);

        var (messagesToSend, injectedAutoApprovals) = this.PrepareStoredAutoApprovals(messages, session, autoApprovableNames);

        var response = await base.GetResponseAsync(messagesToSend, options, cancellationToken).ConfigureAwait(false);

        // The injected responses are cleared only now that the run has succeeded, so a failed run leaves them in
        // the session and the next run injects them again instead of leaving the tool calls unanswered.
        if (injectedAutoApprovals)
        {
            session.StateBag.TryRemoveValue(StateBagKey);
        }

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

        var autoApprovableNames = ApprovalRequirement.GetApprovalNotRequiredToolNames(this, options);

        var (messagesToSend, injectedAutoApprovals) = this.PrepareStoredAutoApprovals(messages, session, autoApprovableNames);

        List<ToolApprovalRequestContent>? autoApproved = null;

        // Set only once the stream has run to completion, so that any abnormal end - an exception from the inner
        // client, a cancellation, or a consumer that stops enumerating early - leaves the stored state exactly as it
        // was. A caught exception is not enough on its own: breaking out of the enumeration disposes this iterator
        // without throwing, and the run then persists nothing either.
        bool completedNormally = false;

        try
        {
            await foreach (var update in base.GetStreamingResponseAsync(messagesToSend, options, cancellationToken).ConfigureAwait(false))
            {
                if (FilterUpdateContents(update, autoApprovableNames, ref autoApproved))
                {
                    yield return update;
                }
            }

            completedNormally = true;
        }
        finally
        {
            // Both writes are gated, mirroring the non-streaming path: the requests collected here were filtered out
            // of the stream and so never reached the caller, and storing them on an abnormal end would overwrite the
            // batch that was injected this run and still needs re-injecting.
            if (completedNormally)
            {
                if (injectedAutoApprovals)
                {
                    session.StateBag.TryRemoveValue(StateBagKey);
                }

                if (autoApproved is { Count: > 0 })
                {
                    session.StateBag.SetValue(StateBagKey, autoApproved, AgentJsonUtilities.DefaultOptions);
                }
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

    [LoggerMessage(LogLevel.Warning, "A tool call to '{ToolName}' was stored for automatic approval on a previous turn, but the tool available under that name now requires approval or is no longer available. The stored approval is discarded and the call is rejected rather than executed.")]
    private static partial void LogStaleAutoApprovalRejected(ILogger logger, string toolName);

    /// <summary>
    /// Checks the session for stored auto-approvals from a previous turn and decides, per stored request and
    /// against the tools available to the current turn, whether it can still be injected as approved.
    /// </summary>
    /// <remarks>
    /// <para>
    /// A stored request records that a tool did not require approval at the time the decision was made, which
    /// made the decision the framework's to take on the caller's behalf. Approval requirements can change
    /// between turns, so each stored request is re-checked before it is used. If the tool that would now run
    /// requires approval, or is no longer available at all, the stored decision no longer stands and the call is
    /// injected as rejected instead of approved, so that it is not executed.
    /// </para>
    /// <para>
    /// A tool being replaced between turns is not in itself a reason to reject anything, and routinely happens as
    /// an agent is developed. Only a change in whether approval is required matters here.
    /// </para>
    /// </remarks>
    /// <returns>
    /// The messages to send to the inner client, and whether any responses were injected into them. The stored
    /// auto-approvals are cleared by the caller only once the run has completed successfully, so that a failed
    /// run leaves them in the session and the next run injects them again rather than leaving the calls
    /// unanswered.
    /// </returns>
    private (IEnumerable<ChatMessage> Messages, bool Injected) PrepareStoredAutoApprovals(
        IEnumerable<ChatMessage> messages,
        AgentSession session,
        HashSet<string> autoApprovableNames)
    {
        if (!session.StateBag.TryGetValue(
            StateBagKey,
            out List<ToolApprovalRequestContent>? pendingRequests,
            AgentJsonUtilities.DefaultOptions)
            || pendingRequests is not { Count: > 0 })
        {
            return (messages, false);
        }

        // We have some requests that didn't require approval on the last run.
        // Let's check each one to make sure they didn't become approval required in the meantime.
        List<AIContent> approvalResponses = [];

        foreach (var request in pendingRequests)
        {
            bool stillApprovalNotRequired = ApprovalRequirement.IsApprovalNotRequired(request.ToolCall, autoApprovableNames);

            if (!stillApprovalNotRequired)
            {
                LogStaleAutoApprovalRejected(this._logger, (request.ToolCall as FunctionCallContent)?.Name ?? "unknown");
            }

            approvalResponses.Add(request.CreateResponse(approved: stillApprovalNotRequired));
        }

        return (messages.Concat([new ChatMessage(ChatRole.User, approvalResponses)]), true);
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
                    && ApprovalRequirement.IsApprovalNotRequired(approval.ToolCall, autoApprovableNames))
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

                if (ApprovalRequirement.IsApprovalNotRequired(approval.ToolCall, autoApprovableNames))
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
