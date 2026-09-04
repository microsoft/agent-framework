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
/// exists to signal. The adapter therefore reports a conversation id on every response so that a protocol-conformant
/// caller sends only the new messages on subsequent turns instead of resending the whole history into a session that
/// is already accumulating it. That id is a single constant for the lifetime of the adapter: the value the caller
/// supplied, or one generated per instance. It never varies with the response, the session, or the service.
/// </para>
/// <para>
/// Because the reported id never changes, the promise that every id it reports is an id it accepts back holds
/// trivially. The id is per instance rather than a shared constant, so an id minted by one adapter cannot be replayed
/// against another. When the caller echoes it back it is stripped before the agent sees it, which restores the
/// as-if-absent semantics of the first turn; a fixed bound session cannot fork, so an absent id means "continue this
/// conversation" rather than "start a new one".
/// </para>
/// <para>
/// Service-side conversation ids are not surfaced in bound mode at all. Responses and streamed updates are copied and
/// re-stamped, so an id minted by the service is replaced rather than forwarded, and the session's own id is not
/// reported either. The session tracks the service conversation internally; callers that need to address a specific
/// service conversation should bind a session obtained from
/// <see cref="ChatClientAgent.CreateSessionAsync(string, CancellationToken)"/>. Consequently the session's service
/// conversation id is not an accepted input either; only the id this adapter hands out is.
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
    /// The one conversation id this adapter ever reports, or <see langword="null"/> when the adapter is stateless and
    /// therefore has no conversation to name.
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
    /// The one conversation id to report on every response and update when <paramref name="session"/> is non-null. If
    /// <see langword="null"/>, an id unique to this instance is generated. Ignored when <paramref name="session"/> is
    /// <see langword="null"/>, since a stateless adapter names no conversation.
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

        // An id exists exactly when a session is bound. Without one the caller owns the history, so the response is
        // already conformant and is returned untouched, preserving the identity the inner client established.
        return this._conversationId is { } conversationId
            ? CloneWithConversationId(response, conversationId)
            : response;
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
    /// In bound mode every update is re-stamped with the adapter's single conversation id, so whatever the service
    /// does with its own ids mid-stream cannot change what the caller is told. The stamp is applied to a copy, so the
    /// inner client's own updates are left unmodified.
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

            if (this._conversationId is not { } conversationId)
            {
                yield return converted;
                continue;
            }

            // The update belongs to the inner client, so the id is stamped on a copy rather than in place.
            var stamped = converted.Clone();
            stamped.ConversationId = conversationId;
            yield return stamped;
        }

        if (!yieldedAnyUpdate && this._conversationId is { } trailingConversationId)
        {
            // A bound run that produced nothing would otherwise aggregate to a null conversation id, which under the
            // IChatClient contract means "no stored history" and invites the caller to resend everything into a
            // session that is already accumulating it. One id-only update repairs the aggregate.
            //
            // This is reachable only on the zero-update stream: the branch above stamps a non-null id on every update
            // whenever a session is bound, so any stream that yielded at all has already carried the id to the caller.
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
    /// A bound adapter was given a conversation id other than the one it reports.
    /// </exception>
    /// <remarks>
    /// <para>
    /// A bound adapter reports exactly one id and accepts exactly that id, so the check is a single comparison. The
    /// session's own service conversation id is not accepted: it is never reported either, and honoring an id the
    /// adapter does not hand out would let a caller steer the run by an identifier it was never given.
    /// </para>
    /// <para>
    /// The rejection message deliberately names only the caller's own value. This adapter is expected to sit behind
    /// hosts that surface exceptions to untrusted callers, so echoing accepted ids back would let a caller harvest
    /// them by probing.
    /// </para>
    /// <para>
    /// A blank id is read as an absent one. Transports routinely materialize an omitted field as an empty string, and
    /// the id this adapter hands out is never blank, so treating blank as unknown would reject the caller for
    /// following the very advice the rejection gives.
    /// </para>
    /// <para>
    /// A stateless adapter interprets nothing: the id, like every other option, is the caller's to set and is passed
    /// through untouched.
    /// </para>
    /// </remarks>
    private ChatOptions? ResolveRequestOptions(ChatOptions? options)
    {
        // No id of this adapter's own means no session and so nothing to interpret. A blank incoming id names no
        // conversation and is treated exactly as an absent one: reuse the bound session.
        if (this._conversationId is not { } conversationId ||
            options?.ConversationId is not { } incomingId ||
            string.IsNullOrWhiteSpace(incomingId))
        {
            return options;
        }

        if (incomingId == conversationId)
        {
            // The caller is echoing the id this adapter reported. Removing it restores the as-if-absent semantics of
            // the first turn, which the bound session interprets as "continue".
            var stripped = options.Clone();
            stripped.ConversationId = null;
            return stripped;
        }

        // Only the caller's own value is named. The accepted id is a live conversation identifier and this message may
        // reach an untrusted caller through a host, so disclosing it would turn the error into an oracle.
        throw new InvalidOperationException(
            $"The supplied {nameof(ChatOptions)}.{nameof(ChatOptions.ConversationId)} '{incomingId}' is not a known conversation id for this " +
            $"{nameof(AIAgentExtensions.AsIChatClient)} client. Send back the conversation id from the most recent response, or omit it to " +
            "continue the bound conversation. To converse over a different existing service conversation, bind the client to a session " +
            $"obtained from {nameof(ChatClientAgent)}.{nameof(ChatClientAgent.CreateSessionAsync)}(conversationId).");
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
