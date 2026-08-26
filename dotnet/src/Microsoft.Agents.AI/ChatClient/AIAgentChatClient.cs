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
/// This is what keeps the adapter's central promise: every id it reports is an id it accepts back.
/// </para>
/// <para>
/// The adapter's own id is per instance rather than a constant, so an id minted by an adapter over one session cannot
/// be replayed against an adapter over another. When the caller echoes it back it is stripped before the agent sees
/// it, which restores the as-if-absent semantics of the first turn; a fixed bound session cannot fork, so an absent
/// id means "continue this conversation" rather than "start a new one".
/// </para>
/// <para>
/// Streaming applies the same test to every update, re-reading the session as it goes, so updates streamed before the
/// session learns a service id carry the adapter's id and later ones carry the service id. The two entry points can
/// therefore disagree on the first turn of a service-backed conversation, where the identical non-streaming call
/// reports the just-learned service id throughout. Both ids are accepted on the following turn, so a caller that
/// simply echoes what it was given is unaffected.
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
        if (knownServiceConversationId is not null)
        {
            return response.ConversationId == knownServiceConversationId
                ? response
                : CloneWithConversationId(response, knownServiceConversationId);
        }

        // No real id anywhere. Any id the response still carries is one the session does not stand behind, such as
        // the local-history sentinel, and reporting it would hand back an id the next request would have to reject.
        // Reporting this adapter's own id keeps the promise that whatever is reported is also accepted.
        return CloneWithConversationId(response, this._conversationId!);
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
    /// point on. Deciding from the stream instead would break the adapter's promise that every id it reports is one it
    /// accepts back: the agent records a service id on the session only after its update loop completes, so a consumer
    /// that stops enumerating early would be handed an id the session never learned and the next call would reject.
    /// </para>
    /// </remarks>
    private async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseCoreAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        var updates = this._agent.RunStreamingAsync(messages, this._session, ToAgentRunOptions(options), cancellationToken);

        await foreach (var update in updates.ConfigureAwait(false))
        {
            var converted = update.AsChatResponseUpdate();

            // Re-read per update so that an id the session learns mid-run is picked up rather than missed.
            var knownServiceConversationId = this.KnownServiceConversationId;

            if (this._session is null ||
                (converted.ConversationId is { } conversationId && conversationId == knownServiceConversationId))
            {
                yield return converted;
                continue;
            }

            // The update belongs to the inner client, so the id is stamped on a copy rather than in place. On a bound
            // session the adapter's own id is never null, so every update leaves here carrying an acceptable id.
            var stamped = converted.Clone();
            stamped.ConversationId = knownServiceConversationId ?? this._conversationId;
            yield return stamped;
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
    /// A bound adapter was given a conversation id naming neither the conversation it reports nor the bound session's
    /// service conversation.
    /// </exception>
    /// <remarks>
    /// A stateless adapter interprets nothing: the id, like every other option, is the caller's to set and is passed
    /// through untouched.
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

        if (incomingId == this._conversationId)
        {
            // The caller is echoing the id this adapter reported. Removing it restores the as-if-absent semantics of
            // the first turn, which the bound session interprets as "continue".
            var stripped = options.Clone();
            stripped.ConversationId = null;
            return stripped;
        }

        throw new InvalidOperationException(
            $"The supplied {nameof(ChatOptions)}.{nameof(ChatOptions.ConversationId)} '{incomingId}' does not name the conversation this " +
            $"{nameof(AIAgentExtensions.AsIChatClient)} adapter is bound to. It accepts the conversation id reported on its responses ('{this._conversationId}')" +
            (knownServiceConversationId is null ? string.Empty : $" and the bound session's service conversation id ('{knownServiceConversationId}')") +
            ". To converse over a different existing service conversation, bind the adapter to a session obtained from " +
            $"{nameof(ChatClientAgent)}.{nameof(ChatClientAgent.CreateSessionAsync)}(conversationId).");
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
