// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>A builder for creating pipelines of <see cref="AIAgent"/>.</summary>
public sealed class AIAgentBuilder
{
    private readonly Func<IServiceProvider, AIAgent> _innerAgentFactory;

    /// <summary>The registered agent factory instances.</summary>
    private List<Func<AIAgent, IServiceProvider, AIAgent>>? _agentFactories;

    /// <summary>Initializes a new instance of the <see cref="AIAgentBuilder"/> class.</summary>
    /// <param name="innerAgent">The inner <see cref="AIAgent"/> that represents the underlying backend.</param>
    /// <exception cref="ArgumentNullException"><paramref name="innerAgent"/> is <see langword="null"/>.</exception>
    public AIAgentBuilder(AIAgent innerAgent)
    {
        _ = Throw.IfNull(innerAgent);
        this._innerAgentFactory = _ => innerAgent;
    }

    /// <summary>Initializes a new instance of the <see cref="AIAgentBuilder"/> class.</summary>
    /// <param name="innerAgentFactory">A callback that produces the inner <see cref="AIAgent"/> that represents the underlying backend.</param>
    public AIAgentBuilder(Func<IServiceProvider, AIAgent> innerAgentFactory)
    {
        this._innerAgentFactory = Throw.IfNull(innerAgentFactory);
    }

    /// <inheritdoc/>
    public AIAgent Build(IServiceProvider? services = null)
    {
        services ??= EmptyServiceProvider.Instance;
        var agent = this._innerAgentFactory(services);

        // To match intuitive expectations, apply the factories in reverse order, so that the first factory added is the outermost.
        if (this._agentFactories is not null)
        {
            for (var i = this._agentFactories.Count - 1; i >= 0; i--)
            {
                agent = this._agentFactories[i](agent, services);
                if (agent is null)
                {
                    Throw.InvalidOperationException(
                        $"The {nameof(AIAgentBuilder)} entry at index {i} returned null. " +
                        $"Ensure that the callbacks passed to {nameof(Use)} return non-null {nameof(AIAgent)} instances.");
                }
            }
        }

        return agent;
    }

    /// <inheritdoc/>
    public AIAgentBuilder Use(Func<AIAgent, AIAgent> agentFactory)
    {
        _ = Throw.IfNull(agentFactory);

        return this.Use((innerAgent, _) => agentFactory(innerAgent));
    }

    /// <inheritdoc/>
    public AIAgentBuilder Use(Func<AIAgent, IServiceProvider, AIAgent> agentFactory)
    {
        _ = Throw.IfNull(agentFactory);

        (this._agentFactories ??= []).Add(agentFactory);
        return this;
    }

    /// <summary>
    /// Provides an empty <see cref="IServiceProvider"/> implementation.
    /// </summary>
    private sealed class EmptyServiceProvider : IServiceProvider, IKeyedServiceProvider
    {
        /// <summary>Gets the singleton instance of <see cref="EmptyServiceProvider"/>.</summary>
        public static EmptyServiceProvider Instance { get; } = new();

        /// <inheritdoc/>
        public object? GetService(Type serviceType) => null;

        /// <inheritdoc/>
        public object? GetKeyedService(Type serviceType, object? serviceKey) => null;

        /// <inheritdoc/>
        public object GetRequiredKeyedService(Type serviceType, object? serviceKey) =>
            throw new InvalidOperationException($"No service for type '{serviceType}' has been registered.");
    }
}
