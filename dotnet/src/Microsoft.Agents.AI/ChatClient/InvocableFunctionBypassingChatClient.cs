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
/// A delegating chat client that lets an agent expose both invocable (backend) tools and
/// declaration-only (frontend) tools at the same time, working around
/// <see cref="FunctionInvokingChatClient"/> terminating the function-calling loop before invoking
/// sibling backend tool calls when a declaration-only tool call appears in the same iteration.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="FunctionInvokingChatClient"/> terminates the loop as soon as it encounters a
/// non-invocable (declaration-only) <see cref="FunctionCallContent"/>, returning every
/// <see cref="FunctionCallContent"/> in that iteration — including invocable backend calls — to the
/// caller unexecuted.
/// </para>
/// <para>
/// This decorator sits above <see cref="FunctionInvokingChatClient"/> in the pipeline. On outbound
/// responses that contain <em>both</em> an invocable (backend) <see cref="FunctionCallContent"/> and a
/// declaration-only <see cref="FunctionCallContent"/>, it removes the invocable calls from the response,
/// stores them in the session's <see cref="AgentSessionStateBag"/>, and returns only the declaration-only
/// calls to the caller to resolve. On the next request — after the caller has resolved the
/// declaration-only calls — the stored invocable calls are re-injected as pre-approved
/// <see cref="ToolApprovalResponseContent"/> so that <see cref="FunctionInvokingChatClient"/> reconstructs
/// and executes them, producing the missing <see cref="FunctionResultContent"/>.
/// </para>
/// <para>
/// The stored calls are re-injected as approved <see cref="ToolApprovalResponseContent"/> rather than as
/// bare <see cref="FunctionCallContent"/> because <see cref="FunctionInvokingChatClient"/> only re-executes
/// calls that arrive from incoming history as approval responses; it does not execute bare
/// <see cref="FunctionCallContent"/> present in the history. This is the same mechanism used by
/// <see cref="ApprovalNotRequiredFunctionBypassingChatClient"/>, and a lone approved response without a
/// matching request in the history is accepted.
/// </para>
/// <para>
/// This decorator operates within the context of a running <see cref="AIAgent"/> with an active
/// <see cref="AgentRunContext.Session"/>. When invoked without an ambient run context or session
/// (for example when the chat client is used directly outside of an agent run), the decorator becomes
/// a no-op: it passes the request through to the inner client unchanged and logs a warning.
/// </para>
/// <para>
/// When the pipeline also contains an <see cref="ApprovalResponseBindingChatClient"/>, this decorator must sit
/// <em>below</em> it. That client drops any <see cref="ToolApprovalResponseContent"/> without a request it
/// recorded, so that a forged approval cannot execute; the responses injected here are synthetic and have no
/// such request. The default agent pipeline already orders them correctly.
/// </para>
/// </remarks>
internal sealed partial class InvocableFunctionBypassingChatClient : DelegatingChatClient
{
    /// <summary>
    /// The key used in <see cref="AgentSessionStateBag"/> to store bypassed invocable function calls
    /// between agent runs.
    /// </summary>
    internal const string StateBagKey = "_bypassedInvocableFunctionCalls";

    private readonly ILogger _logger;

    private bool _warnedNoSession;

    /// <summary>
    /// Initializes a new instance of the <see cref="InvocableFunctionBypassingChatClient"/> class.
    /// </summary>
    /// <param name="innerClient">The underlying chat client (typically a <see cref="FunctionInvokingChatClient"/>).</param>
    /// <param name="loggerFactory">An optional <see cref="ILoggerFactory"/> used to create a logger for diagnostics.</param>
    public InvocableFunctionBypassingChatClient(IChatClient innerClient, ILoggerFactory? loggerFactory = null)
        : base(innerClient)
    {
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<InvocableFunctionBypassingChatClient>();
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

        messages = InjectPendingBypassedCalls(messages, session);

        var response = await base.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false);

        this.RemoveAndStoreBypassableInvocableCalls(response.Messages, options, session);

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

        messages = InjectPendingBypassedCalls(messages, session);

        // Stream updates live until a surfaced (non-informational) FunctionCallContent appears, then hold the
        // tail so the strip/store decision can observe every call in the same batch before re-emitting.
        // No whole-response coalescing is required because FunctionInvokingChatClient emits each call as a
        // complete FunctionCallContent (it never splits a call across updates).
        //
        // FunctionInvokingChatClient buffers per iteration: it yields its buffered updates at the end of each
        // iteration and then streams the next iteration live. When it invokes a call locally it flips
        // FunctionCallContent.InformationalOnly to true in place, on the very instances held here. A buffered
        // tail whose calls have all become informational therefore has nothing left to strip, so it is
        // released and live streaming resumes. Only a genuinely bypassable batch (where the loop terminated,
        // leaving the calls non-informational) is held to the end of the stream.
        List<ChatResponseUpdate>? tail = null;

        await foreach (var update in base.GetStreamingResponseAsync(messages, options, cancellationToken).ConfigureAwait(false))
        {
            if (tail is not null && !ContainsNonInformationalFunctionCall(tail))
            {
                foreach (var buffered in tail)
                {
                    yield return buffered;
                }

                tail = null;
            }

            if (tail is null && !UpdateHasNonInformationalFunctionCall(update))
            {
                yield return update;
                continue;
            }

            (tail ??= []).Add(update);
        }

        if (tail is null)
        {
            yield break;
        }

        var contentLists = new IList<AIContent>[tail.Count];
        for (int i = 0; i < tail.Count; i++)
        {
            contentLists[i] = tail[i].Contents;
        }

        this.StripAndStoreBypassableInvocableCalls(contentLists, options, session);

        // Every buffered update is surfaced, including any left with no contents by the stripping above. An
        // update carries metadata beyond its contents — ConversationId, ContinuationToken, ResponseId,
        // MessageId, RawRepresentation and more — so dropping one would discard state the caller needs, and a
        // content-free update is unremarkable in a stream. This differs from the non-streaming path, where an
        // emptied message is removed because it would otherwise be persisted to history and resent to the
        // provider on the next turn.
        foreach (var update in tail)
        {
            yield return update;
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

    [LoggerMessage(LogLevel.Warning, "InvocableFunctionBypassingChatClient was invoked without an active agent run context or session. Invocable function bypassing is skipped and all function calls are surfaced to the caller. Invoke the chat client through AIAgent.RunAsync or AIAgent.RunStreamingAsync to enable bypassing.")]
    private static partial void LogBypassingSkipped(ILogger logger);

    /// <summary>
    /// Checks the session for invocable function calls stored on a previous turn and injects them as
    /// a user message containing pre-approved <see cref="ToolApprovalResponseContent"/> items appended to
    /// the input messages, so that <see cref="FunctionInvokingChatClient"/> reconstructs and executes them.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Pending calls are consumed exactly once: the session entry is removed here and is never put back, so a
    /// turn that fails or whose stream is abandoned drops them.
    /// </para>
    /// <para>
    /// That is deliberate. The calls are injected as one batch and the service expects a
    /// <see cref="FunctionResultContent"/> for every <see cref="FunctionCallContent"/> in it.
    /// <see cref="FunctionInvokingChatClient"/> invokes approved approval responses before the main loop and
    /// before any downstream service call, so by the time a request fails part of the batch has usually
    /// already run — and because a failure surfaces as an exception rather than a response, the results of
    /// those invocations are unrecoverable. Re-injecting the remainder would therefore still leave the batch
    /// incomplete while invoking already-executed functions a second time. Dropping the calls avoids the
    /// duplicate invocation, and matches
    /// <see cref="ApprovalNotRequiredFunctionBypassingChatClient"/>, which likewise never restores its entry.
    /// </para>
    /// </remarks>
    /// <param name="messages">The outgoing messages.</param>
    /// <param name="session">The session holding any calls bypassed on a previous turn.</param>
    private static IEnumerable<ChatMessage> InjectPendingBypassedCalls(
        IEnumerable<ChatMessage> messages,
        AgentSession session)
    {
        if (!session.StateBag.TryGetValue(
            StateBagKey,
            out List<FunctionCallContent>? pendingCalls,
            AgentJsonUtilities.DefaultOptions)
            || pendingCalls is not { Count: > 0 })
        {
            return messages;
        }

        session.StateBag.TryRemoveValue(StateBagKey);

        List<AIContent> approvalResponses = [];
        foreach (var call in pendingCalls)
        {
            // FunctionInvokingChatClient reconstructs and executes the call from the approval response
            // itself; the request is synthetic and does not need to be present in the history.
            var request = new ToolApprovalRequestContent(ComposeApprovalRequestId(call.CallId), call);
            approvalResponses.Add(request.CreateResponse(approved: true));
        }

        var userMessage = new ChatMessage(ChatRole.User, approvalResponses);
        return messages.Concat([userMessage]);
    }

    /// <summary>
    /// Composes the approval-request id for a bypassed call. The prefix deliberately differs from the
    /// <c>ficc_</c> prefix <see cref="FunctionInvokingChatClient"/> uses for its own approval requests, so
    /// that a synthetic id can never collide with a genuine one.
    /// </summary>
    private static string ComposeApprovalRequestId(string callId) => $"ifbcc_{callId}";

    /// <summary>
    /// Builds the set of invocable (backend) tool names and the set of declaration-only (frontend) tool
    /// names from <see cref="ChatOptions.Tools"/> and <see cref="FunctionInvokingChatClient.AdditionalTools"/>.
    /// </summary>
    private (HashSet<string> Invocable, HashSet<string> DeclarationOnly) GetToolNameSets(ChatOptions? options)
    {
        var ficc = this.GetService<FunctionInvokingChatClient>();

        var allTools = (options?.Tools ?? Enumerable.Empty<AITool>())
            .Concat(ficc?.AdditionalTools ?? Enumerable.Empty<AITool>());

        HashSet<string> invocable = new(StringComparer.Ordinal);
        HashSet<string> declarationOnly = new(StringComparer.Ordinal);

        foreach (var tool in allTools)
        {
            // AIFunction derives from AIFunctionDeclaration, so check the invocable type first.
            if (tool is AIFunction function)
            {
                invocable.Add(function.Name);
            }
            else if (tool is AIFunctionDeclaration declaration)
            {
                declarationOnly.Add(declaration.Name);
            }
        }

        return (invocable, declarationOnly);
    }

    /// <summary>
    /// Returns <see langword="true"/> if the update contains a non-informational
    /// <see cref="FunctionCallContent"/> (a call that was surfaced to the caller rather than executed by
    /// <see cref="FunctionInvokingChatClient"/>).
    /// </summary>
    private static bool UpdateHasNonInformationalFunctionCall(ChatResponseUpdate update)
        => update.Contents.Any(c => c is FunctionCallContent { InformationalOnly: false });

    /// <summary>
    /// Returns <see langword="true"/> if any content list contains a non-informational
    /// <see cref="FunctionCallContent"/> (a call that was surfaced to the caller rather than executed by
    /// <see cref="FunctionInvokingChatClient"/>).
    /// </summary>
    private static bool ContainsNonInformationalFunctionCall(IList<AIContent>[] contentLists)
        => contentLists.Any(contents => contents.Any(c => c is FunctionCallContent { InformationalOnly: false }));

    /// <summary>
    /// Returns <see langword="true"/> if any buffered update still contains a non-informational
    /// <see cref="FunctionCallContent"/>. Once <see cref="FunctionInvokingChatClient"/> has invoked a call it
    /// flips <see cref="FunctionCallContent.InformationalOnly"/> to <see langword="true"/> in place, so a
    /// buffer for which this returns <see langword="false"/> holds nothing that can be bypassed.
    /// </summary>
    private static bool ContainsNonInformationalFunctionCall(List<ChatResponseUpdate> updates)
        => updates.Any(UpdateHasNonInformationalFunctionCall);

    /// <summary>
    /// When a response contains both an invocable (backend) <see cref="FunctionCallContent"/> and a
    /// declaration-only (frontend) <see cref="FunctionCallContent"/>, removes the invocable calls from the
    /// response and stores them in the session for re-injection and execution on the next request.
    /// </summary>
    private void RemoveAndStoreBypassableInvocableCalls(
        IList<ChatMessage> messages,
        ChatOptions? options,
        AgentSession session)
    {
        var contentLists = new IList<AIContent>[messages.Count];
        for (int i = 0; i < messages.Count; i++)
        {
            contentLists[i] = messages[i].Contents;
        }

        var emptied = this.StripAndStoreBypassableInvocableCalls(contentLists, options, session);
        if (emptied is null)
        {
            return;
        }

        // Remove messages that were emptied by stripping bypassed content (high index first). Messages that
        // were already empty (for example metadata-only messages) are left untouched. Unlike a streaming
        // update, an emptied message is worth removing because it would otherwise be persisted to the
        // conversation history and resent to the provider on the next turn.
        for (int i = messages.Count - 1; i >= 0; i--)
        {
            if (emptied.Contains(i))
            {
                messages.RemoveAt(i);
            }
        }
    }

    /// <summary>
    /// Applies the both-kinds gate over the supplied content lists and, when both an invocable and a
    /// declaration-only <see cref="FunctionCallContent"/> are present, removes the invocable calls in place
    /// (in document order) and stores them in the session for re-injection on the next request.
    /// </summary>
    /// <returns>
    /// The set of content-list indices that were emptied by the removal, or <see langword="null"/> when
    /// nothing was bypassed.
    /// </returns>
    private HashSet<int>? StripAndStoreBypassableInvocableCalls(
        IList<AIContent>[] contentLists,
        ChatOptions? options,
        AgentSession session)
    {
        // Cheap first pass: the common case is a text-only response with no function calls. Avoid allocating
        // the tool-name sets unless the response actually contains at least one non-informational call.
        if (!ContainsNonInformationalFunctionCall(contentLists))
        {
            return null;
        }

        var (invocable, declarationOnly) = this.GetToolNameSets(options);

        if (invocable.Count == 0 || declarationOnly.Count == 0)
        {
            // The mixed backend/frontend scenario is impossible without at least one of each kind of tool.
            return null;
        }

        bool hasInvocableCall = false;
        bool hasDeclarationOnlyCall = false;

        foreach (var contents in contentLists)
        {
            foreach (var content in contents)
            {
                if (content is FunctionCallContent { InformationalOnly: false } fcc)
                {
                    if (declarationOnly.Contains(fcc.Name))
                    {
                        hasDeclarationOnlyCall = true;
                    }
                    else if (invocable.Contains(fcc.Name))
                    {
                        hasInvocableCall = true;
                    }
                }
            }
        }

        // Only bypass when the two kinds coexist in the same response. An all-invocable response is already
        // handled by FunctionInvokingChatClient (never surfaced unexecuted), and an all-declaration-only
        // response is the normal frontend-tools flow that must pass through unchanged.
        if (!hasInvocableCall || !hasDeclarationOnlyCall)
        {
            return null;
        }

        List<FunctionCallContent>? bypassed = null;
        HashSet<int>? emptied = null;

        for (int i = 0; i < contentLists.Length; i++)
        {
            var contents = contentLists[i];
            bool removedFromList = false;

            // Forward scan collects the bypassed calls in document order.
            for (int j = 0; j < contents.Count;)
            {
                if (contents[j] is FunctionCallContent { InformationalOnly: false } fcc
                    && invocable.Contains(fcc.Name)
                    && !declarationOnly.Contains(fcc.Name))
                {
                    (bypassed ??= []).Add(fcc);
                    contents.RemoveAt(j);
                    removedFromList = true;
                }
                else
                {
                    j++;
                }
            }

            if (removedFromList && contents.Count == 0)
            {
                (emptied ??= []).Add(i);
            }
        }

        if (bypassed is { Count: > 0 })
        {
            session.StateBag.SetValue(StateBagKey, bypassed, AgentJsonUtilities.DefaultOptions);
        }

        return emptied;
    }
}
