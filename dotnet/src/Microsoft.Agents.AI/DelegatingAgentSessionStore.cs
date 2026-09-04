// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an abstract base class for agent session stores that delegate operations to an inner store
/// instance while allowing for extensibility and customization.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="DelegatingAgentSessionStore"/> implements the decorator pattern for <see cref="AgentSessionStore"/>s,
/// enabling the creation of pipelines where each layer can add functionality while delegating core operations to an
/// underlying store.
/// </para>
/// <para>
/// The default implementation provides transparent pass-through behavior, forwarding all operations to the inner store.
/// Derived classes can override specific methods to add custom behavior while maintaining compatibility with the store
/// interface.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public abstract class DelegatingAgentSessionStore : AgentSessionStore
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DelegatingAgentSessionStore"/> class with the specified inner
    /// store.
    /// </summary>
    /// <param name="innerStore">The underlying session store instance that will handle the core operations.</param>
    /// <exception cref="ArgumentNullException"><paramref name="innerStore"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// The inner session store serves as the foundation of the delegation chain. All operations not overridden by
    /// derived classes will be forwarded to this store.
    /// </remarks>
    protected DelegatingAgentSessionStore(AgentSessionStore innerStore)
    {
        this.InnerStore = Throw.IfNull(innerStore);
    }

    /// <summary>
    /// Gets the inner session store instance that receives delegated operations.
    /// </summary>
    /// <value>
    /// The underlying <see cref="AgentSessionStore"/> instance that handles core storage operations.
    /// </value>
    /// <remarks>
    /// Derived classes can use this property to access the inner session store for custom delegation scenarios
    /// or to forward operations with additional processing.
    /// </remarks>
    protected AgentSessionStore InnerStore { get; }

    /// <inheritdoc/>
    public override ValueTask<AgentSession?> GetSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default)
        => this.InnerStore.GetSessionAsync(agent, key, cancellationToken);

    /// <inheritdoc/>
    public override ValueTask SaveSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        AgentSession session,
        CancellationToken cancellationToken = default)
        => this.InnerStore.SaveSessionAsync(agent, key, session, cancellationToken);
}
