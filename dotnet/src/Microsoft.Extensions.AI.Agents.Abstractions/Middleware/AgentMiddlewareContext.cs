// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Base class for callback middleware context that provides common functionality for all agent callback contexts.
/// </summary>
public abstract class AgentMiddlewareContext
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentMiddlewareContext"/> class.
    /// </summary>
    /// <param name="agent">The agent instance associated with this context.</param>
    /// <param name="cancellationToken">The cancellation token for the operation.</param>
    protected AgentMiddlewareContext(AIAgent agent, CancellationToken cancellationToken)
    {
        this.Agent = Throw.IfNull(agent);
        this.CancellationToken = cancellationToken;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentMiddlewareContext"/> class by copying properties from the provided.
    /// </summary>
    /// <param name="other"></param>
    internal AgentMiddlewareContext(AgentMiddlewareContext other)
    {
        this.Agent = other.Agent;
        this.CancellationToken = other.CancellationToken;
    }

    /// <summary>
    /// Gets the agent instance associated with this context.
    /// </summary>
    public AIAgent Agent { get; }

    /// <summary>
    /// Gets the cancellation token for the operation.
    /// </summary>
    public CancellationToken CancellationToken { get; }
}
