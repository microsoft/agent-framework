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
/// <see cref="ChatClientBuilder"/> pipelines or <see cref="ChatClientExtensions"/> helpers. The contract it presents
/// — what it reports, what it accepts and what it rejects, in both stateless and session-bound mode — is documented on
/// <see cref="AIAgentExtensions.AsIChatClient"/>, the only entry point through which this type is constructed. What
/// follows is the reasoning behind the implementation rather than a second statement of that contract.
/// </para>
/// <para>
/// The invariant everything else serves is that every conversation id this adapter reports is one it accepts back. A
/// bound adapter therefore reports a single fixed id rather than anything derived from the response, the session or the
/// service, and, when the caller supplies none, mints it per instance, so a generated id handed out by an adapter bound
/// to one session cannot be replayed against an adapter bound to another.
/// </para>
/// <para>
/// The same invariant is why a stateless adapter clears ids instead of forwarding them. The case that makes that
/// load-bearing is <see cref="ChatClientAgent"/>'s own session: turn this adapter back into an agent with
/// <see cref="ChatClientExtensions.AsAIAgent(IChatClient, ChatClientAgentOptions?, Microsoft.Extensions.Logging.ILoggerFactory?, IServiceProvider?)"/>
/// and that session records whatever conversation id the client below it reported, then sends it back on the next turn
/// — straight into a rejection, were an id ever reported that this adapter does not accept. The same mechanism, a
/// caller round-tripping a reported id, recurs throughout the stack, <see cref="FunctionInvokingChatClient"/> and
/// <see cref="MessageInjectingChatClient"/> included. One consequence is that the
/// <see cref="PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId"/> sentinel, which marks history
/// as handled in process rather than naming a resumable conversation, is surfaced in neither mode: bound mode replaces
/// it with the adapter's own id, and stateless mode clears it.
/// </para>
/// <para>
/// An incoming blank id is normalized to null rather than passed along; see <see cref="ResolveRequestOptions"/> for
/// what forwarding one would cost.
/// </para>
/// <para>
/// Nothing is rewritten in place. Responses and updates belong to the inner client and callers rely on getting them
/// back as they were, so an id is stamped or cleared on a copy and the inner instance travels on only when there is
/// nothing to change. <see cref="ChatResponse"/> exposes no <c>Clone</c> of its own, so that copy is member-wise by
/// hand, and the set of members it covers is pinned by <c>ChatResponse_SettableMembersMatchTheConversationIdStampCopySet</c>
/// in <c>AIAgentChatClientTests</c>, which fails if the type gains or loses a settable member.
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

        // The reported id is always this adapter's own: the single bound id, or none at all when stateless. Applying
        // it means a copy, because the response belongs to the inner client — stamped in bound mode, cleared in
        // stateless mode. Only when there is nothing to change is the instance returned as it stands, which preserves
        // the identity the inner client established.
        return this._conversationId is null && response.ConversationId is null
            ? response
            : CloneWithConversationId(response, this._conversationId);
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
    /// does with its own ids mid-stream cannot change what the caller is told. In stateless mode there is no id to
    /// report, so an update that arrives carrying one has it cleared instead; an update that carries none is passed
    /// through as it stands. Either way the change is applied to a copy, so the inner client's own updates are left
    /// unmodified.
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

            if (this._conversationId is null && converted.ConversationId is null)
            {
                // Nothing to change, so the converted instance travels on as it stands.
                yield return converted;
            }
            else
            {
                // Bound mode stamps its single id, stateless mode clears whatever the update arrived with. Either way
                // the change lands on a copy, because the update belongs to the inner client.
                var restamped = converted.Clone();
                restamped.ConversationId = this._conversationId;
                yield return restamped;
            }
        }

        if (!yieldedAnyUpdate && this._conversationId is { } trailingConversationId)
        {
            // A bound run that produced nothing would otherwise aggregate to a null conversation id, which under the
            // IChatClient contract means "no stored history" and invites the caller to resend everything into a
            // session that is already accumulating it. One id-only update repairs the aggregate.
            //
            // This is reachable only on the zero-update stream: when a session is bound the loop above stamps the
            // adapter's non-null id on every update it yields, so any stream that yielded at all has already carried
            // the id to the caller.
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
    /// The options to forward: <paramref name="options"/> itself unless a conversation id has to be removed, which is
    /// done on a copy so that the caller's own instance is never mutated. An id is removed when it is blank, which is
    /// normalized to absent, and when it is the adapter's own id echoed back, which is stripped.
    /// </returns>
    /// <exception cref="InvalidOperationException">
    /// A bound adapter was given a non-blank conversation id other than the one it reports, or a stateless adapter was
    /// given a non-blank conversation id at all.
    /// </exception>
    /// <remarks>
    /// <para>
    /// The rule either mode enforces is the same one: the adapter never accepts an id it did not hand out. A bound
    /// adapter hands out exactly one, so the check is a single comparison; the session's own service conversation id is
    /// not among them, since honoring an id the adapter never gave the caller would let the caller steer the run by an
    /// identifier it was never shown. A stateless adapter hands out none, so there is nothing for it to accept and
    /// every non-blank id is rejected. Forwarding one instead would let an untrusted caller name a service-side
    /// conversation of its choosing and have the agent read and extend it under the host's credentials.
    /// </para>
    /// <para>
    /// The rejection message deliberately names only the caller's own value. This adapter is expected to sit behind
    /// hosts that surface exceptions to untrusted callers, so echoing accepted ids back would let a caller harvest
    /// them by probing.
    /// </para>
    /// <para>
    /// A blank id is read as an absent one and cleared before the agent sees it. Transports routinely materialize an
    /// omitted field as an empty string, and the id this adapter hands out is never blank, so treating blank as
    /// unknown would reject the caller for following the very advice the rejection gives. Forwarding it as it stands
    /// would be no better: downstream blankness checks use <see cref="string.IsNullOrEmpty(string?)"/> rather than
    /// <see cref="string.IsNullOrWhiteSpace(string?)"/>, so a whitespace id would be read there as naming a
    /// service-managed conversation, and an empty one would suppress the id the agent is configured with.
    /// </para>
    /// <para>
    /// To address a specific service conversation, bind a session obtained from
    /// <see cref="ChatClientAgent.CreateSessionAsync(string, CancellationToken)"/>, which is the one route by which a
    /// conversation id legitimately enters this adapter.
    /// </para>
    /// </remarks>
    private ChatOptions? ResolveRequestOptions(ChatOptions? options)
    {
        if (options?.ConversationId is not { } incomingId)
        {
            return options;
        }

        if (string.IsNullOrWhiteSpace(incomingId))
        {
            // Blank names no conversation, and forwarding it as it stands is not neutral; see the remarks above.
            return WithoutConversationId(options);
        }

        if (this._conversationId is not { } conversationId)
        {
            // Stateless: this adapter hands out no id, so there is none it can take back. The message names the
            // caller's own value and the route that does accept an id; unlike the bound rejection below there is
            // nothing here to withhold, because this adapter accepts no id at all.
            throw new InvalidOperationException(
                $"The supplied {nameof(ChatOptions)}.{nameof(ChatOptions.ConversationId)} '{incomingId}' cannot be used: this " +
                $"{nameof(AIAgentExtensions.AsIChatClient)} client is not bound to a session, so it has no conversation to continue and does " +
                "not accept a conversation id. Send the full history on every call, or bind a session with " +
                $"agent.{nameof(AIAgentExtensions.AsIChatClient)}(session); to continue an existing service conversation, bind a session " +
                $"obtained from {nameof(ChatClientAgent)}.{nameof(ChatClientAgent.CreateSessionAsync)}(conversationId).");
        }

        if (incomingId == conversationId)
        {
            // The caller is echoing the id this adapter reported. Removing it restores the as-if-absent semantics of
            // the first turn, which the bound session interprets as "continue".
            return WithoutConversationId(options);
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
    /// Creates a copy of <paramref name="options"/> carrying no conversation id.
    /// </summary>
    /// <param name="options">The options to copy.</param>
    /// <returns>
    /// A copy of <paramref name="options"/> whose <see cref="ChatOptions.ConversationId"/> is <see langword="null"/>.
    /// </returns>
    /// <remarks>
    /// The caller owns the instance it supplied and may reuse it across calls, so an id is removed on a copy rather
    /// than in place.
    /// </remarks>
    private static ChatOptions WithoutConversationId(ChatOptions options)
    {
        var copy = options.Clone();
        copy.ConversationId = null;
        return copy;
    }

    /// <summary>
    /// Creates a copy of <paramref name="response"/> carrying the specified conversation id.
    /// </summary>
    /// <param name="response">The response to copy.</param>
    /// <param name="conversationId">
    /// The conversation id to report on the copy, or <see langword="null"/> to report none, which is what a stateless
    /// adapter does with an id the agent's raw response carried.
    /// </param>
    /// <returns>A new <see cref="ChatResponse"/> equivalent to <paramref name="response"/> apart from its conversation id.</returns>
    /// <remarks>
    /// <para>
    /// The response belongs to the inner client, and callers rely on getting that instance back unmodified, so the id
    /// is never stamped in place. <see cref="ChatResponse"/> exposes no <c>Clone</c> of its own, hence the explicit
    /// member-wise copy; reference-type members, <see cref="ChatResponse.RawRepresentation"/> included, are shared
    /// rather than duplicated so that everything reachable from the original stays reachable from the copy.
    /// </para>
    /// <para>
    /// The set of members copied here is pinned by
    /// <c>ChatResponse_SettableMembersMatchTheConversationIdStampCopySet</c> in <c>AIAgentChatClientTests</c>, which
    /// fails if <see cref="ChatResponse"/> ever gains or loses a settable member.
    /// </para>
    /// </remarks>
    private static ChatResponse CloneWithConversationId(ChatResponse response, string? conversationId) =>
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
