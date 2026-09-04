// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// A delegating <see cref="AgentSessionStore"/> that adds an isolation partition from an
/// <see cref="AgentIsolationKeyProvider"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public class IsolationKeyScopedAgentSessionStore : DelegatingAgentSessionStore
{
    private const string IsolationPartitionName = "isolation";

    private readonly AgentIsolationKeyProvider? _keyProvider;
    private readonly bool _strict;

    /// <summary>
    /// Initializes a new instance of the <see cref="IsolationKeyScopedAgentSessionStore"/> class.
    /// </summary>
    /// <param name="innerStore">The underlying <see cref="AgentSessionStore"/> to delegate to.</param>
    /// <param name="keyProvider">
    /// The <see cref="AgentIsolationKeyProvider"/> used to retrieve the isolation key for the current context.
    /// </param>
    /// <param name="options">The options for configuring the session store. If null, defaults are used.</param>
    /// <exception cref="ArgumentNullException">
    /// <paramref name="innerStore"/> is <see langword="null"/>.
    /// </exception>
    public IsolationKeyScopedAgentSessionStore(
        AgentSessionStore innerStore,
        AgentIsolationKeyProvider? keyProvider,
        IsolationKeyScopedAgentSessionStoreOptions? options = null)
        : base(innerStore)
    {
        this._keyProvider = keyProvider;
        options ??= new IsolationKeyScopedAgentSessionStoreOptions();
        this._strict = options.Strict;
    }

    /// <summary>
    /// Asynchronously retrieves the isolation key from the provider and validates it if in strict mode.
    /// </summary>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>
    /// The isolation key string, or <see langword="null"/> if no key is available and non-strict mode is enabled.
    /// </returns>
    /// <exception cref="InvalidOperationException">
    /// The provider returned <see langword="null"/> and strict mode is enabled.
    /// </exception>
    private async ValueTask<string?> GetIsolationKeyAsync(CancellationToken cancellationToken)
    {
        string? key = this._keyProvider != null
                    ? await this._keyProvider.GetIsolationKeyAsync(cancellationToken).ConfigureAwait(false)
                    : null;

        if (string.IsNullOrWhiteSpace(key))
        {
            if (this._strict)
            {
                throw new InvalidOperationException("Agent isolation key is required but was not provided by the configured AgentIsolationKeyProvider.");
            }

            return null;
        }

        return key;
    }

    /// <summary>
    /// Adds the isolation value from the current hosting context to the session key.
    /// </summary>
    private async ValueTask<AgentSessionStoreKey> GetScopedKeyAsync(
        AgentSessionStoreKey key,
        CancellationToken cancellationToken)
    {
        _ = Throw.IfNull(key);

        string? isolationKey = await this.GetIsolationKeyAsync(cancellationToken).ConfigureAwait(false);
        return isolationKey is null ? key : key.WithPartition(IsolationPartitionName, isolationKey);
    }

    /// <inheritdoc />
    public override async ValueTask<AgentSession?> GetSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default)
    {
        AgentSessionStoreKey scopedKey = await this.GetScopedKeyAsync(key, cancellationToken).ConfigureAwait(false);
        return await this.InnerStore.GetSessionAsync(agent, scopedKey, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public override async ValueTask<AgentSession> GetOrCreateSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default)
    {
        AgentSessionStoreKey scopedKey = await this.GetScopedKeyAsync(key, cancellationToken).ConfigureAwait(false);
        return await this.InnerStore.GetOrCreateSessionAsync(agent, scopedKey, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public override async ValueTask SaveSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        AgentSession session,
        CancellationToken cancellationToken = default)
    {
        AgentSessionStoreKey scopedKey = await this.GetScopedKeyAsync(key, cancellationToken).ConfigureAwait(false);
        await this.InnerStore.SaveSessionAsync(agent, scopedKey, session, cancellationToken).ConfigureAwait(false);
    }
}
