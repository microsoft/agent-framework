// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides a hosting wrapper around an <see cref="AIAgent"/> that adds session persistence capabilities
/// for server-hosted scenarios where conversations need to be restored across requests.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="AIHostAgent"/> wraps an existing agent implementation and adds the ability to
/// persist and restore conversation threads using an <see cref="AgentSessionStore"/>.
/// </para>
/// <para>
/// This wrapper enables session persistence without requiring type-specific knowledge of the session type,
/// as all session operations work through the base <see cref="AgentSession"/> abstraction.
/// </para>
/// </remarks>
public class AIHostAgent : DelegatingAIAgent
{
    private readonly AgentSessionStore _sessionStore;
    private string? _capturedIsolationKey;

    /// <summary>
    /// Initializes a new instance of the <see cref="AIHostAgent"/> class.
    /// </summary>
    /// <param name="innerAgent">The underlying agent implementation to wrap.</param>
    /// <param name="sessionStore">The session store to use for persisting conversation state.</param>
    /// <param name="sessionStorageIdentity">
    /// The optional logical hosting identity used only to partition persisted sessions across agent instances.
    /// It does not replace <see cref="AIAgent.Id"/> or <see cref="AIAgent.Name"/>.
    /// </param>
    /// <exception cref="ArgumentNullException">
    /// <paramref name="innerAgent"/> or <paramref name="sessionStore"/> is <see langword="null"/>.
    /// </exception>
    public AIHostAgent(
        AIAgent innerAgent,
        AgentSessionStore sessionStore,
        string? sessionStorageIdentity = null)
        : base(innerAgent)
    {
        this._sessionStore = Throw.IfNull(sessionStore);
        this.SessionStorageIdentity = sessionStorageIdentity is null
            ? null
            : Throw.IfNullOrWhitespace(sessionStorageIdentity);
    }

    /// <summary>
    /// Gets the stable logical identity used to partition session storage, or <see langword="null"/> when
    /// session storage follows the wrapped agent instance identity.
    /// </summary>
    internal string? SessionStorageIdentity { get; }

    /// <summary>
    /// Gets an existing agent session for the specified conversation, or creates a new one if none exists.
    /// </summary>
    /// <param name="conversationId">The unique identifier of the conversation for which to retrieve or create the agent session. Cannot be null,
    /// empty, or consist only of white-space characters.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the asynchronous operation.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains the agent session associated with the
    /// specified conversation. If no session exists, a new session is created and returned.</returns>
    public ValueTask<AgentSession> GetOrCreateSessionAsync(string conversationId, CancellationToken cancellationToken = default)
        => this.GetOrCreateSessionAsync(new AgentSessionStoreKey(conversationId), cancellationToken);

    /// <summary>
    /// Gets an existing agent session for the specified storage key, or creates a new one if none exists.
    /// </summary>
    /// <param name="key">The key that identifies and partitions the session.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the asynchronous operation.</param>
    /// <returns>A task whose result contains the stored or newly created agent session.</returns>
    public ValueTask<AgentSession> GetOrCreateSessionAsync(
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(key);

        MarkFeatureUsed();
        return this._capturedIsolationKey is null
            ? this._sessionStore.GetOrCreateSessionAsync(this, key, cancellationToken)
            : this.GetOrCreateSessionWithCapturedIsolationKeyAsync(key, cancellationToken);
    }

    /// <summary>
    /// Persists a conversation session to the session store.
    /// </summary>
    /// <param name="conversationId">The unique identifier for the conversation.</param>
    /// <param name="session">The session to persist.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task that represents the asynchronous save operation.</returns>
    /// <exception cref="ArgumentException"><paramref name="conversationId"/> is null or whitespace.</exception>
    /// <exception cref="ArgumentNullException"><paramref name="session"/> is <see langword="null"/>.</exception>
    public ValueTask SaveSessionAsync(string conversationId, AgentSession session, CancellationToken cancellationToken = default)
        => this.SaveSessionAsync(new AgentSessionStoreKey(conversationId), session, cancellationToken);

    /// <summary>
    /// Persists a session under the specified storage key.
    /// </summary>
    /// <param name="key">The key that identifies and partitions the session.</param>
    /// <param name="session">The session to persist.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task that represents the asynchronous save operation.</returns>
    public ValueTask SaveSessionAsync(
        AgentSessionStoreKey key,
        AgentSession session,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(key);
        _ = Throw.IfNull(session);

        MarkFeatureUsed();
        return this._capturedIsolationKey is null
            ? this._sessionStore.SaveSessionAsync(this, key, session, cancellationToken)
            : this.SaveSessionWithCapturedIsolationKeyAsync(key, session, cancellationToken);
    }

    /// <summary>
    /// Creates a host agent whose isolation-aware session store uses a key captured from the originating request.
    /// </summary>
    /// <param name="isolationKey">The trusted caller isolation key, or <see langword="null"/> when isolation does not apply.</param>
    /// <returns>
    /// A host agent bound to <paramref name="isolationKey"/>, or this instance when its store does not use
    /// <see cref="IsolationKeyScopedAgentSessionStore"/> anywhere in its decorator pipeline or no key was supplied.
    /// </returns>
    public AIHostAgent BindIsolationKey(string? isolationKey)
    {
        if (isolationKey is null ||
            this._sessionStore.GetService<IsolationKeyScopedAgentSessionStore>() is null)
        {
            return this;
        }

        // Keep the configured decorator pipeline intact. Session operations flow the captured key
        // to the isolation layer when they reach it, even when other decorators wrap that layer.
        var boundAgent = new AIHostAgent(this.InnerAgent, this._sessionStore, this.SessionStorageIdentity);
        boundAgent._capturedIsolationKey = Throw.IfNullOrWhitespace(isolationKey);
        return boundAgent;
    }

    private async ValueTask<AgentSession> GetOrCreateSessionWithCapturedIsolationKeyAsync(
        AgentSessionStoreKey key,
        CancellationToken cancellationToken)
    {
        using IDisposable isolationScope =
            IsolationKeyScopedAgentSessionStore.UseCapturedIsolationKey(this._capturedIsolationKey!);
        return await this._sessionStore.GetOrCreateSessionAsync(this, key, cancellationToken).ConfigureAwait(false);
    }

    private async ValueTask SaveSessionWithCapturedIsolationKeyAsync(
        AgentSessionStoreKey key,
        AgentSession session,
        CancellationToken cancellationToken)
    {
        using IDisposable isolationScope =
            IsolationKeyScopedAgentSessionStore.UseCapturedIsolationKey(this._capturedIsolationKey!);
        await this._sessionStore.SaveSessionAsync(this, key, session, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        MarkFeatureUsed();
        return base.RunCoreAsync(messages, session, options, cancellationToken);
    }

    /// <inheritdoc />
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        MarkFeatureUsed();
        await foreach (AgentResponseUpdate update in base.RunCoreStreamingAsync(messages, session, options, cancellationToken).ConfigureAwait(false))
        {
            yield return update;
        }
    }

    private static void MarkFeatureUsed()
    {
#pragma warning disable MAAI001
        FeatureUsage.MarkUsed((int)FeatureIndex.HostingAgent);
#pragma warning restore MAAI001
    }
}
