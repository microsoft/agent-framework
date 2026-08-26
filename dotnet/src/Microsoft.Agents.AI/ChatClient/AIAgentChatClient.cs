// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="IChatClient"/> implementation that delegates all of its operations to an <see cref="AIAgent"/>.
/// </summary>
/// <remarks>
/// <para>
/// This adapter is the inverse of <see cref="ChatClientAgent"/>: rather than building an agent on top of a chat client,
/// it exposes an existing agent to any component that consumes the <see cref="IChatClient"/> abstraction, such as
/// <see cref="ChatClientBuilder"/> pipelines or <see cref="ChatClientExtensions"/> helpers.
/// </para>
/// <para>
/// Without a session the adapter is stateless and behaves exactly like any other <see cref="IChatClient"/>: the caller
/// owns the history and supplies it in full on every call, and nothing about the conversation id is interpreted.
/// </para>
/// <para>
/// With a bound session the history is stored by the session, which is what <see cref="ChatResponse.ConversationId"/>
/// exists to signal. The adapter therefore reports a non-null conversation id on every response so that a
/// protocol-conformant caller sends only the new messages on subsequent turns instead of resending the whole history
/// into a session that is already accumulating it. Which id is reported follows from the session, not from the
/// response:
/// <list type="bullet">
/// <item><description>
/// If the session holds a service conversation id, that real id is reported, and a response already carrying it is
/// returned exactly as the agent produced it rather than copied.
/// </description></item>
/// <item><description>
/// Otherwise the adapter reports an id of its own, standing for "this adapter over this session". A response may still
/// carry an id here — an in-process sentinel, or a raw id the session does not stand behind — but reporting it would
/// hand the caller an id the next request would have to reject.
/// </description></item>
/// </list>
/// This is what keeps the adapter's central promise: every id it reports is an id it accepts back. Acceptance covers
/// three values — the adapter's own id, the session's current service conversation id, and the id most recently
/// reported. The last is needed because services commonly fork the conversation on each turn, advancing the session's
/// id after an id has already been handed out; without it, a caller echoing exactly what it was given would be
/// rejected.
/// </para>
/// <para>
/// The adapter's own id is per instance rather than a constant, so an id minted by an adapter over one session cannot
/// be replayed against an adapter over another. When the caller echoes back any accepted id it is stripped before the
/// agent sees it, which restores the as-if-absent semantics of the first turn; a fixed bound session cannot fork, so
/// an absent id means "continue this conversation" rather than "start a new one". An echoed id the session has since
/// superseded therefore resolves transparently to the current conversation rather than failing.
/// </para>
/// <para>
/// Streaming applies the same test to every update, re-reading the session as it goes, so updates streamed before the
/// session adopts a service id carry the adapter's id and later ones carry the service id. The two entry points can
/// therefore report different ids for the same call whenever the service mints or advances an id during the run — the
/// first turn of a service-backed conversation is only the most obvious case, and a service that forks per turn does
/// it on every turn. Streaming may consequently report an id the session has already superseded by the time the
/// caller replies; echoing it back is accepted and resolved to the current conversation.
/// </para>
/// <para>
/// A bound run that yields no updates at all ends with one final update carrying nothing but the conversation id, so
/// that aggregating the stream still reports stored history rather than an absent id.
/// </para>
/// <para>
/// A session-bound adapter supports one in-flight request at a time. Concurrent calls over the same bound session
/// race on the session's history state, which is not synchronized, so the caller is responsible for serializing them.
/// </para>
/// <para>
/// The adapter does not own the lifetime of the wrapped agent or session, so <see cref="Dispose"/> is a no-op.
/// </para>
/// </remarks>
internal sealed class AIAgentChatClient : IChatClient
{
    /// <summary>The agent to which all operations are delegated.</summary>
    private readonly AIAgent _agent;

    /// <summary>The optional session to use for every request, or <see langword="null"/> to operate statelessly.</summary>
    private readonly AgentSession? _session;

    /// <summary>
    /// The conversation id this adapter reports when no service-managed id is available, or <see langword="null"/>
    /// when the adapter is stateless and therefore has no conversation to name.
    /// </summary>
    /// <remarks>
    /// Deliberately per instance rather than a shared constant: a constant would let an adapter bound to one session
    /// accept an id minted by an adapter bound to a different session.
    /// </remarks>
    private readonly string? _conversationId;

    /// <summary>Lazily-created metadata synthesized from the agent's <see cref="AIAgentMetadata"/>.</summary>
    private ChatClientMetadata? _metadata;

    /// <summary>
    /// The conversation id most recently reported to a caller, or <see langword="null"/> if none has been.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Services that fork a conversation per turn hand out a new id on every call, and the bound session adopts it as
    /// the run ends. Without this field, an id reported mid-stream would stop being recognized the moment the session
    /// moved on, and a caller echoing back exactly what it was given would be rejected. Remembering it keeps the
    /// acceptance set aligned with what was actually reported rather than with what the session happens to hold now.
    /// </para>
    /// <para>
    /// A plain field write is sufficient because a session-bound adapter serves one request at a time, which the
    /// caller is required to guarantee; the acceptance window is only as well-defined as that constraint.
    /// </para>
    /// </remarks>
    private string? _lastReportedConversationId;

    /// <summary>
    /// Initializes a new instance of the <see cref="AIAgentChatClient"/> class.
    /// </summary>
    /// <param name="agent">The agent to which all operations are delegated. Must not be <see langword="null"/>.</param>
    /// <param name="session">
    /// The optional <see cref="AgentSession"/> to use for every request. If <see langword="null"/>, each request is
    /// made without a session, and the caller is responsible for supplying the full conversation history.
    /// </param>
    /// <param name="conversationId">
    /// The conversation id to report when <paramref name="session"/> is non-null and no service-managed id is
    /// available. If <see langword="null"/>, an id unique to this instance is generated.
    /// </param>
    /// <remarks>
    /// The arguments are validated by <see cref="AIAgentExtensions.AsIChatClient"/>, the only entry point through
    /// which this internal type is constructed.
    /// </remarks>
    public AIAgentChatClient(AIAgent agent, AgentSession? session, string? conversationId)
    {
        this._agent = agent;
        this._session = session;

        // No session means no stored history and so nothing to name; an id is only minted for the bound case.
        this._conversationId = session is null ? null : conversationId ?? Guid.NewGuid().ToString("N");
    }

    /// <summary>
    /// Gets the service-managed conversation id the bound session has learned, or <see langword="null"/> if there is
    /// none.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Only <see cref="ChatClientAgentSession"/> is recognized. Sessions of other agent types that track a service
    /// conversation internally are not detected, and such an adapter reports its own id instead.
    /// </para>
    /// <para>
    /// Two session values are deliberately read as "no id". A blank id names nothing, matching how
    /// <see cref="ChatClientAgent"/> itself tests session conversation ids. And
    /// <see cref="PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId"/> is a sentinel stamped on
    /// responses, streamed updates, and the session whenever
    /// <see cref="ChatClientAgentOptions.RequirePerServiceCallChatHistoryPersistence"/> is enabled; it exists to tell
    /// <see cref="FunctionInvokingChatClient"/> that history is handled downstream and names no conversation any
    /// caller can resume, so this adapter must not pass it off as one.
    /// </para>
    /// </remarks>
    private string? KnownServiceConversationId
    {
        get
        {
            var sessionConversationId = this._session?.GetService<ChatClientAgentSession>()?.ConversationId;

            return string.IsNullOrWhiteSpace(sessionConversationId) ||
                sessionConversationId == PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId
                    ? null
                    : sessionConversationId;
        }
    }

    /// <inheritdoc/>
    public async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        options = this.ResolveRequestOptions(options);

        var response = (await this._agent.RunAsync(messages, this._session, ToAgentRunOptions(options), cancellationToken).ConfigureAwait(false))
            .AsChatResponse();

        if (this._session is null)
        {
            // The caller owns the history, so the response is already conformant and is returned untouched,
            // preserving the identity the inner client established.
            return response;
        }

        // Read after the run: the agent records a service-managed id on the session as the run ends, so a real id
        // the response introduced on this very turn is already visible here.
        var knownServiceConversationId = this.KnownServiceConversationId;

        // With no real id anywhere, any id the response still carries is one the session does not stand behind, such
        // as the local-history sentinel, so this adapter's own id is reported instead.
        var resolved =
            knownServiceConversationId is null ? CloneWithConversationId(response, this._conversationId!) :
            response.ConversationId == knownServiceConversationId ? response :
            CloneWithConversationId(response, knownServiceConversationId);

        this._lastReportedConversationId = resolved.ConversationId;
        return resolved;
    }

    /// <inheritdoc/>
    public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        // This method is deliberately not an iterator so that argument validation happens
        // when the method is called rather than when the resulting sequence is enumerated.
        _ = Throw.IfNull(messages);

        return this.GetStreamingResponseCoreAsync(messages, this.ResolveRequestOptions(options), cancellationToken);
    }

    /// <summary>
    /// Streams the agent's response, converting each <see cref="AgentResponseUpdate"/> to a <see cref="ChatResponseUpdate"/>.
    /// </summary>
    /// <param name="messages">The messages to send to the agent.</param>
    /// <param name="options">The chat options to apply to the run, already resolved by <see cref="ResolveRequestOptions"/>.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>An asynchronous sequence of <see cref="ChatResponseUpdate"/> instances.</returns>
    /// <remarks>
    /// <para>
    /// <paramref name="cancellationToken"/> is annotated with <see cref="EnumeratorCancellationAttribute"/> so that a
    /// token supplied by the consumer at enumeration time, via <c>WithCancellation</c>, also reaches the agent. Without
    /// the annotation such a token would be silently dropped.
    /// </para>
    /// <para>
    /// Each update is judged against the session, exactly as <see cref="GetResponseAsync"/> judges a response: an id is
    /// passed through only when the session stands behind it, and anything else is replaced. The session is consulted
    /// per update rather than once up front, so a service id learned part-way through the run is honored from that
    /// point on. What the probe buys is that the adapter never advertises an id the session cannot serve — the
    /// local-history sentinel, or a raw id the session does not recognize — because such an id names no conversation
    /// this adapter could resume. Reporting from the stream alone would advertise exactly those. The
    /// <see cref="_lastReportedConversationId"/> field is a safety net for ids that go stale after being reported, not
    /// a licence to report ids the session never backed in the first place.
    /// </para>
    /// </remarks>
    private async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseCoreAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        var updates = this._agent.RunStreamingAsync(messages, this._session, ToAgentRunOptions(options), cancellationToken);

        var yieldedAnyUpdate = false;

        await foreach (var update in updates.ConfigureAwait(false))
        {
            var converted = update.AsChatResponseUpdate();
            yieldedAnyUpdate = true;

            // Re-read per update so that an id the session learns mid-run is picked up rather than missed.
            var knownServiceConversationId = this.KnownServiceConversationId;

            if (this._session is null ||
                (converted.ConversationId is { } conversationId && conversationId == knownServiceConversationId))
            {
                this._lastReportedConversationId = converted.ConversationId;
                yield return converted;
                continue;
            }

            // The update belongs to the inner client, so the id is stamped on a copy rather than in place. On a bound
            // session the adapter's own id is never null, so every update leaves here carrying an acceptable id.
            var stamped = converted.Clone();
            stamped.ConversationId = knownServiceConversationId ?? this._conversationId;
            this._lastReportedConversationId = stamped.ConversationId;
            yield return stamped;
        }

        if (this._session is not null && !yieldedAnyUpdate)
        {
            // A bound run that produced nothing would otherwise aggregate to a null conversation id, which under the
            // IChatClient contract means "no stored history" and invites the caller to resend everything into a
            // session that is already accumulating it. One id-only update repairs the aggregate.
            //
            // This is reachable only on the zero-update stream: both branches above report a non-null id whenever a
            // session is bound, so any stream that yielded at all has already carried the id to the caller.
            var trailingConversationId = this.KnownServiceConversationId ?? this._conversationId;
            this._lastReportedConversationId = trailingConversationId;

            yield return new ChatResponseUpdate { ConversationId = trailingConversationId };
        }
    }

    /// <inheritdoc/>
    public object? GetService(Type serviceType, object? serviceKey = null)
    {
        _ = Throw.IfNull(serviceType);

        if (serviceKey is null && serviceType.IsInstanceOfType(this))
        {
            return this;
        }

        if (this._agent.GetService(serviceType, serviceKey) is { } service)
        {
            return service;
        }

        if (serviceKey is null && serviceType == typeof(ChatClientMetadata))
        {
            // A race here is benign: concurrent callers may each build an equivalent instance, and the
            // reference assignment is atomic, so every caller still observes a fully-constructed object.
            return this._metadata ??= new ChatClientMetadata(this._agent.GetService<AIAgentMetadata>()?.ProviderName);
        }

        return null;
    }

    /// <inheritdoc/>
    /// <remarks>
    /// This adapter does not own the lifetime of the underlying <see cref="AIAgent"/> or <see cref="AgentSession"/>,
    /// so disposing it has no effect and is safe to perform any number of times.
    /// </remarks>
    public void Dispose()
    {
        // Intentionally a no-op: the adapter does not own the agent or session it wraps.
    }

    /// <summary>
    /// Interprets the <see cref="ChatOptions.ConversationId"/> a caller supplied and produces the options to forward
    /// to the agent.
    /// </summary>
    /// <param name="options">The chat options supplied by the caller, or <see langword="null"/> if none were.</param>
    /// <returns>
    /// The options to forward: <paramref name="options"/> itself in every case except the echoed adapter id, which is
    /// stripped from a copy so that the caller's own instance is never mutated.
    /// </returns>
    /// <exception cref="InvalidOperationException">
    /// A bound adapter was given a conversation id naming none of the conversations it accepts.
    /// </exception>
    /// <remarks>
    /// <para>
    /// A bound adapter accepts three ids: its own, the session's current service conversation id, and the id it most
    /// recently reported. The last of these matters because a service that forks the conversation each turn advances
    /// the session's id out from under an id already handed to the caller; without it, echoing back exactly what was
    /// reported would be rejected.
    /// </para>
    /// <para>
    /// A stale echo is self-healing rather than authoritative: stripping it leaves the agent to continue the bound
    /// session, which already holds the current id, and the resulting response reports that current id.
    /// </para>
    /// <para>
    /// The rejection message deliberately names only the caller's own id. The accepted ids are live conversation
    /// identifiers, and this adapter is expected to sit behind hosts that surface exceptions to untrusted callers, so
    /// echoing them back would let a caller harvest them by probing.
    /// </para>
    /// <para>
    /// A stateless adapter interprets nothing: the id, like every other option, is the caller's to set and is passed
    /// through untouched.
    /// </para>
    /// </remarks>
    private ChatOptions? ResolveRequestOptions(ChatOptions? options)
    {
        if (this._session is null || options?.ConversationId is not { } incomingId)
        {
            return options;
        }

        var knownServiceConversationId = this.KnownServiceConversationId;

        // Checked before the adapter's own id so that a caller-supplied conversation id which happens to equal the
        // real service id is handed to ChatClientAgent for its own validation rather than silently stripped.
        if (incomingId == knownServiceConversationId)
        {
            // A real service conversation id that the session already holds; ChatClientAgent validates it against
            // the session itself, so there is nothing to add here.
            return options;
        }

        if (incomingId == this._conversationId || incomingId == this._lastReportedConversationId)
        {
            // The caller is echoing an id this adapter reported, either its own or one the session has since
            // superseded. Removing it restores the as-if-absent semantics of the first turn, which the bound session
            // interprets as "continue" using whichever id it now holds.
            var stripped = options.Clone();
            stripped.ConversationId = null;
            return stripped;
        }

        // Only the caller's own value is named. The accepted ids are live conversation identifiers and this message
        // may reach an untrusted caller through a host, so disclosing them would turn the error into an oracle.
        throw new InvalidOperationException(
            $"The supplied {nameof(ChatOptions)}.{nameof(ChatOptions.ConversationId)} '{incomingId}' does not name a conversation this " +
            $"{nameof(AIAgentExtensions.AsIChatClient)} adapter can serve. Send back the conversation id from the most recent response, or omit " +
            "it to continue the bound conversation. To converse over a different existing service conversation, bind the adapter to a " +
            $"session obtained from {nameof(ChatClientAgent)}.{nameof(ChatClientAgent.CreateSessionAsync)}(conversationId).");
    }

    /// <summary>
    /// Creates a copy of <paramref name="response"/> carrying the specified conversation id.
    /// </summary>
    /// <param name="response">The response to copy.</param>
    /// <param name="conversationId">The conversation id to report on the copy.</param>
    /// <returns>A new <see cref="ChatResponse"/> equivalent to <paramref name="response"/> apart from its conversation id.</returns>
    /// <remarks>
    /// <para>
    /// The response belongs to the inner client, and callers rely on getting that instance back unmodified, so the id
    /// is never stamped in place. <see cref="ChatResponse"/> exposes no <c>Clone</c> of its own, hence the explicit
    /// member-wise copy; reference-type members, <see cref="ChatResponse.RawRepresentation"/> included, are shared
    /// rather than duplicated so that everything reachable from the original stays reachable from the copy.
    /// </para>
    /// <para>
    /// The set of members copied here is pinned by a test that fails if <see cref="ChatResponse"/> ever gains or loses
    /// a settable member.
    /// </para>
    /// </remarks>
    private static ChatResponse CloneWithConversationId(ChatResponse response, string conversationId) =>
        new()
        {
            AdditionalProperties = response.AdditionalProperties,
            ContinuationToken = response.ContinuationToken,
            ConversationId = conversationId,
            CreatedAt = response.CreatedAt,
            FinishReason = response.FinishReason,
            Messages = response.Messages,
            ModelId = response.ModelId,
            RawRepresentation = response.RawRepresentation,
            ResponseId = response.ResponseId,
            Usage = response.Usage,
        };

    /// <summary>
    /// Converts <see cref="ChatOptions"/> into the agent run options understood by agents that support chat options.
    /// </summary>
    /// <param name="options">The chat options to convert, or <see langword="null"/> if none were supplied.</param>
    /// <returns>
    /// A <see cref="ChatClientAgentRunOptions"/> carrying <paramref name="options"/>, or <see langword="null"/> if
    /// <paramref name="options"/> is <see langword="null"/>.
    /// </returns>
    /// <remarks>
    /// <para>
    /// <see cref="ChatOptions.ResponseFormat"/> is additionally surfaced on the base <see cref="AgentRunOptions"/>
    /// so that agents which do not understand <see cref="ChatClientAgentRunOptions"/> can still honor it.
    /// </para>
    /// <para>
    /// It is deliberately the only option copied to the base type. <see cref="AgentRunOptions.ResponseFormat"/> is the
    /// single member whose <see cref="ChatOptions"/> counterpart any agent implementation can meaningfully act on.
    /// <see cref="AgentRunOptions.AllowBackgroundResponses"/> and <see cref="AgentRunOptions.AdditionalProperties"/>
    /// are not mapped: background responses require a session and continuation tokens that do not round-trip through
    /// the <see cref="IChatClient"/> abstraction, and additional properties carry agent-specific semantics that a
    /// caller supplying <see cref="ChatOptions"/> is not expressing.
    /// </para>
    /// </remarks>
    private static ChatClientAgentRunOptions? ToAgentRunOptions(ChatOptions? options) =>
        options is null ? null : new ChatClientAgentRunOptions(options) { ResponseFormat = options.ResponseFormat };
}
