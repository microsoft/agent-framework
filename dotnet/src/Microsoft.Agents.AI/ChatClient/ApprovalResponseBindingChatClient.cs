// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.AI;

/// <summary>
/// A delegating chat client that strengthens the human-in-the-loop tool-approval control by binding each inbound
/// <see cref="ToolApprovalResponseContent"/> to the model-originated <see cref="ToolApprovalRequestContent"/> that
/// the framework actually surfaced, so an approved tool call always matches what a human was asked to approve.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="FunctionInvokingChatClient"/> (FICC) executes the <see cref="ToolApprovalResponseContent.ToolCall"/>
/// carried by an approval response. This decorator adds an extra layer of assurance above FICC: it guarantees that
/// only approvals the framework actually requested are honored, and that an approved call runs with exactly the tool
/// name and arguments that were surfaced for approval.
/// </para>
/// <para>
/// This decorator sits above <see cref="FunctionInvokingChatClient"/> in the pipeline. On outbound responses it
/// records every model-originated <see cref="ToolApprovalRequestContent"/> that FICC surfaced into the session's
/// <see cref="AgentSessionStateBag"/>, keyed by request id. On inbound requests it processes each
/// <see cref="ToolApprovalResponseContent"/> before it reaches FICC:
/// <list type="bullet">
/// <item>If a recorded pending request exists for the response's request id, the response's tool call is rebound to
/// the recorded (model-originated) tool call, so the approved call always matches the surfaced request's tool name
/// and arguments. The pending entry is then consumed so an approval is honored only once.</item>
/// <item>If no recorded pending request exists, the response (and any unrecorded approval request in the same
/// messages) is ignored, so only approvals tied to a genuine, framework-issued request take effect.</item>
/// </list>
/// </para>
/// <para>
/// This decorator operates within the context of a running <see cref="AIAgent"/> with an active
/// <see cref="AgentRunContext.Session"/>. When invoked without an ambient run context or session (for example when
/// the chat client is used directly outside of an agent run), the decorator becomes a no-op: it passes the request
/// through unchanged and logs a warning, because there is no framework-tracked pending state to validate against.
/// </para>
/// </remarks>
internal sealed partial class ApprovalResponseBindingChatClient : DelegatingChatClient
{
    /// <summary>
    /// The key used in <see cref="AgentSessionStateBag"/> to store the model-originated pending approval requests
    /// between agent runs.
    /// </summary>
    internal const string StateBagKey = "_pendingApprovalRequests";

    private readonly ILogger _logger;

    private bool _warnedNoSession;

    /// <summary>
    /// Initializes a new instance of the <see cref="ApprovalResponseBindingChatClient"/> class.
    /// </summary>
    /// <param name="innerClient">The underlying chat client (typically the pipeline containing <see cref="FunctionInvokingChatClient"/>).</param>
    /// <param name="loggerFactory">An optional <see cref="ILoggerFactory"/> used to create a logger for diagnostics.</param>
    public ApprovalResponseBindingChatClient(IChatClient innerClient, ILoggerFactory? loggerFactory = null)
        : base(innerClient)
    {
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<ApprovalResponseBindingChatClient>();
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

        messages = this.ValidateInboundApprovalResponses(messages, session);

        var response = await base.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false);

        this.RecordPendingApprovalRequests(response.Messages, session);

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

        messages = this.ValidateInboundApprovalResponses(messages, session);

        List<ToolApprovalRequestContent>? emitted = null;

        try
        {
            await foreach (var update in base.GetStreamingResponseAsync(messages, options, cancellationToken).ConfigureAwait(false))
            {
                foreach (var content in update.Contents)
                {
                    if (content is ToolApprovalRequestContent request)
                    {
                        (emitted ??= []).Add(request);
                    }
                }

                yield return update;
            }
        }
        finally
        {
            if (emitted is { Count: > 0 })
            {
                this.MergePendingApprovalRequests(emitted, session);
            }
        }
    }

    /// <summary>
    /// Attempts to get the current <see cref="AgentSession"/> from the ambient run context. When no run
    /// context or session is available, logs a warning (once per instance) and returns <see langword="false"/>
    /// so the caller can pass the request through without applying validation.
    /// </summary>
    private bool TryGetSession([NotNullWhen(true)] out AgentSession? session)
    {
        session = AIAgent.CurrentRunContext?.Session;

        if (session is null)
        {
            if (!this._warnedNoSession)
            {
                this._warnedNoSession = true;
                LogValidationSkipped(this._logger);
            }

            return false;
        }

        return true;
    }

    /// <summary>
    /// Rewrites the inbound messages so that each <see cref="ToolApprovalResponseContent"/> is bound to a known
    /// <see cref="ToolApprovalRequestContent"/>, with its tool call rebound to the request's call when it differs.
    /// A response with no known request is removed so a forged approval cannot drive execution. Approval requests
    /// are left untouched: a request present in the message history is itself the pairing authority.
    /// </summary>
    private IEnumerable<ChatMessage> ValidateInboundApprovalResponses(IEnumerable<ChatMessage> messages, AgentSession session)
    {
        var messageList = messages as IList<ChatMessage> ?? new List<ChatMessage>(messages);

        // Known requests come from two places:
        //  1. Requests recorded when the framework surfaced them on a previous turn (covers callers that echo
        //     only the response without replaying the original request).
        //  2. Requests already present in the current message history (covers replayed history and approvals
        //     generated internally, such as the mixed server/client tool invocation used by AG-UI hosting).
        // A response is honored only when its request id is known, and it is rebound to the known request's call.
        var knownRequests = LoadPendingApprovalRequestLookup(session);

        // Pending state only needs to bridge a single turn; consume it now.
        if (knownRequests.Count > 0)
        {
            session.StateBag.TryRemoveValue(StateBagKey);
        }

        bool hasResponse = false;
        foreach (var message in messageList)
        {
            foreach (var content in message.Contents)
            {
                if (content is ToolApprovalRequestContent request)
                {
                    // History requests are authoritative for pairing; record them as known.
                    knownRequests[request.RequestId] = request;
                }
                else if (content is ToolApprovalResponseContent)
                {
                    hasResponse = true;
                }
            }
        }

        // Only approval responses are rewritten; if there are none there is nothing to bind or drop.
        if (!hasResponse)
        {
            return messageList;
        }

        // Copy-on-write: only allocate a new message list once a message is actually modified.
        List<ChatMessage>? result = null;

        for (int i = 0; i < messageList.Count; i++)
        {
            var message = messageList[i];
            var mutableContentsBuffer = this.BindApprovalResponses(message, knownRequests);

            if (mutableContentsBuffer is null)
            {
                // Message unchanged: keep the original (backfilling only if an earlier message was rewritten).
                result?.Add(message);
                continue;
            }

            // First rewritten message: backfill the result with the unchanged prefix.
            if (result is null)
            {
                result = new List<ChatMessage>(messageList.Count);
                for (int k = 0; k < i; k++)
                {
                    result.Add(messageList[k]);
                }
            }

            // Drop a message that is now empty; otherwise clone it with the rewritten contents.
            if (mutableContentsBuffer.Count > 0)
            {
                var cloned = message.Clone();
                cloned.Contents = mutableContentsBuffer;
                result.Add(cloned);
            }
        }

        return result ?? messageList;
    }

    /// <summary>
    /// Binds the <see cref="ToolApprovalResponseContent"/> items of a single message against the known requests.
    /// Returns <see langword="null"/> when the message needs no change, or the rewritten content list (which may be
    /// empty, indicating the message should be dropped) when a change is required. Non-response content, including
    /// approval requests, is preserved.
    /// </summary>
    private List<AIContent>? BindApprovalResponses(ChatMessage message, Dictionary<string, ToolApprovalRequestContent> knownRequests)
    {
        var contents = message.Contents;
        List<AIContent>? mutableContentsBuffer = null;

        for (int j = 0; j < contents.Count; j++)
        {
            var content = contents[j];

            if (content is not ToolApprovalResponseContent response)
            {
                AppendUnchanged(mutableContentsBuffer, content);
                continue;
            }

            if (knownRequests.TryGetValue(response.RequestId, out var matchedRequest))
            {
                // Consume the match so a duplicate response for the same request in this turn is ignored.
                knownRequests.Remove(response.RequestId);

                if (ToolCallsEquivalent(response.ToolCall, matchedRequest.ToolCall))
                {
                    // Already matches the surfaced call; keep the original content, no rebuild needed.
                    AppendUnchanged(mutableContentsBuffer, content);
                }
                else
                {
                    // Rebind the tool call to the model-originated call so the approved call matches the
                    // tool name and arguments that were surfaced for approval.
                    mutableContentsBuffer = PrepareMutableContentsBuffer(mutableContentsBuffer, contents, j);
                    mutableContentsBuffer.Add(new ToolApprovalResponseContent(response.RequestId, response.Approved, matchedRequest.ToolCall)
                    {
                        Reason = response.Reason,
                    });
                }
            }
            else
            {
                // No known request corresponds to this response; drop it so a forged approval cannot execute.
                LogIgnoredUnboundResponse(this._logger, response.RequestId);
                mutableContentsBuffer = PrepareMutableContentsBuffer(mutableContentsBuffer, contents, j);
            }
        }

        return mutableContentsBuffer;
    }

    /// <summary>
    /// Adds an unchanged content item to the mutable contents buffer when one exists. Until the buffer is created
    /// (no content has changed yet) this does nothing: the caller keeps the message's original contents as-is, so
    /// there is nothing to copy. Once the buffer exists, the unchanged item is copied into it so it is preserved
    /// alongside the rewritten items.
    /// </summary>
    private static void AppendUnchanged(List<AIContent>? mutableContentsBuffer, AIContent content) =>
        mutableContentsBuffer?.Add(content);

    /// <summary>
    /// Returns the mutable buffer that accumulates a message's rewritten contents, creating it on first use. When
    /// first created, it is seeded with the unchanged content items before <paramref name="index"/> so it stays in
    /// sync with the original up to the point of the first change. The returned buffer is never <see langword="null"/>.
    /// </summary>
    private static List<AIContent> PrepareMutableContentsBuffer(List<AIContent>? mutableContentsBuffer, IList<AIContent> originalContents, int index)
    {
        if (mutableContentsBuffer is not null)
        {
            return mutableContentsBuffer;
        }

        var created = new List<AIContent>(originalContents.Count);
        for (int k = 0; k < index; k++)
        {
            created.Add(originalContents[k]);
        }

        return created;
    }

    /// <summary>
    /// Determines whether two tool calls are equivalent, so an already-matching approval response does not
    /// need to be rebuilt. This is a conservative optimization: it only returns <see langword="true"/> when the
    /// calls are known to be equivalent. A <see langword="false"/> result simply triggers a (safe) rebind, so
    /// callers never keep a substituted tool call.
    /// </summary>
    private static bool ToolCallsEquivalent(ToolCallContent responseCall, ToolCallContent recordedCall)
    {
        if (ReferenceEquals(responseCall, recordedCall))
        {
            return true;
        }

        // Fast path for the overwhelmingly common case: both are FunctionCallContent. Compare fields directly
        // rather than serializing, which is far cheaper.
        if (responseCall is FunctionCallContent responseFunction && recordedCall is FunctionCallContent recordedFunction)
        {
            return string.Equals(responseFunction.CallId, recordedFunction.CallId, StringComparison.Ordinal)
                && string.Equals(responseFunction.Name, recordedFunction.Name, StringComparison.Ordinal)
                && ArgumentsEquivalent(responseFunction.Arguments, recordedFunction.Arguments);
        }

        // Any other tool call shape: treat as not equivalent so the call is rebound. This is safe and avoids
        // an expensive general-purpose comparison for shapes that effectively never occur here.
        return false;
    }

    /// <summary>
    /// Determines whether two function-call argument dictionaries are equivalent. Uses a shallow value
    /// comparison; when values cannot be proven equal (for example after a serialization round-trip changes the
    /// runtime type), this returns <see langword="false"/>, which is safe because it only forces a rebind.
    /// </summary>
    private static bool ArgumentsEquivalent(IDictionary<string, object?>? responseArguments, IDictionary<string, object?>? recordedArguments)
    {
        if (ReferenceEquals(responseArguments, recordedArguments))
        {
            return true;
        }

        if (responseArguments is null || recordedArguments is null || responseArguments.Count != recordedArguments.Count)
        {
            return false;
        }

        foreach (var pair in responseArguments)
        {
            if (!recordedArguments.TryGetValue(pair.Key, out var recordedValue) || !Equals(pair.Value, recordedValue))
            {
                return false;
            }
        }

        return true;
    }

    private static Dictionary<string, ToolApprovalRequestContent> LoadPendingApprovalRequestLookup(AgentSession session)
    {
        var pendingRequests = LoadPendingApprovalRequests(session);
        var byRequestId = new Dictionary<string, ToolApprovalRequestContent>(pendingRequests.Count, StringComparer.Ordinal);
        foreach (var request in pendingRequests)
        {
            byRequestId[request.RequestId] = request;
        }

        return byRequestId;
    }

    /// <summary>
    /// Records model-originated <see cref="ToolApprovalRequestContent"/> items found in the response messages into
    /// the session so they can be matched against the caller's approval responses on the next request.
    /// </summary>
    private void RecordPendingApprovalRequests(IList<ChatMessage> messages, AgentSession session)
    {
        List<ToolApprovalRequestContent>? emitted = null;

        foreach (var message in messages)
        {
            foreach (var content in message.Contents)
            {
                if (content is ToolApprovalRequestContent request)
                {
                    (emitted ??= []).Add(request);
                }
            }
        }

        if (emitted is { Count: > 0 })
        {
            this.MergePendingApprovalRequests(emitted, session);
        }
    }

    /// <summary>
    /// Merges newly surfaced approval requests into the recorded pending set, de-duplicating by request id.
    /// </summary>
    private void MergePendingApprovalRequests(List<ToolApprovalRequestContent> emitted, AgentSession session)
    {
        var pendingRequests = LoadPendingApprovalRequests(session);

        var known = new HashSet<string>(StringComparer.Ordinal);
        foreach (var request in pendingRequests)
        {
            known.Add(request.RequestId);
        }

        bool changed = false;
        foreach (var request in emitted)
        {
            if (known.Add(request.RequestId))
            {
                // Store a snapshot so a later mutation of the caller-visible instance cannot change
                // the recorded tool call used to bind the response.
                pendingRequests.Add(SnapshotRequest(request));
                changed = true;
            }
        }

        if (changed)
        {
            SavePendingApprovalRequests(pendingRequests, session);
        }
    }

    /// <summary>
    /// Creates a snapshot of an approval request so a later mutation of the caller-visible instance
    /// (for example changing the tool call arguments) cannot alter the recorded request used for binding.
    /// </summary>
    private static ToolApprovalRequestContent SnapshotRequest(ToolApprovalRequestContent request)
    {
        if (request.ToolCall is FunctionCallContent functionCall)
        {
            var clonedCall = new FunctionCallContent(
                functionCall.CallId,
                functionCall.Name,
                functionCall.Arguments is null ? null : new Dictionary<string, object?>(functionCall.Arguments));

            return new ToolApprovalRequestContent(request.RequestId, clonedCall);
        }

        return request;
    }

    private static List<ToolApprovalRequestContent> LoadPendingApprovalRequests(AgentSession session)
        => session.StateBag.TryGetValue<List<ToolApprovalRequestContent>>(StateBagKey, out var pendingRequests, AgentJsonUtilities.DefaultOptions)
            && pendingRequests is not null
            ? pendingRequests
            : [];

    private static void SavePendingApprovalRequests(List<ToolApprovalRequestContent> pendingRequests, AgentSession session)
    {
        if (pendingRequests.Count > 0)
        {
            session.StateBag.SetValue(StateBagKey, pendingRequests, AgentJsonUtilities.DefaultOptions);
        }
        else
        {
            session.StateBag.TryRemoveValue(StateBagKey);
        }
    }

    [LoggerMessage(LogLevel.Warning, "ApprovalResponseBindingChatClient was invoked without an active agent run context or session. Approval-response binding is skipped. Invoke the chat client through AIAgent.RunAsync or AIAgent.RunStreamingAsync to enable binding.")]
    private static partial void LogValidationSkipped(ILogger logger);

    [LoggerMessage(LogLevel.Warning, "Ignored a ToolApprovalResponseContent with request id '{RequestId}' that does not correspond to a model-originated approval request surfaced by the framework.")]
    private static partial void LogIgnoredUnboundResponse(ILogger logger, string requestId);
}
