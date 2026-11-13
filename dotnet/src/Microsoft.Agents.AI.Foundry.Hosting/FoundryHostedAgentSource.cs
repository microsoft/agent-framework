// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Supplies the one agent a Foundry hosting container serves, from the instance or the factory passed to
/// <c>AddFoundryResponses</c>.
/// </summary>
/// <remarks>
/// <para>
/// Foundry publishes a dedicated endpoint for each hosted agent, so a container serves exactly one agent and a
/// request does not select it. The agent is never registered in dependency injection: the response handler and
/// the readiness checks get it from this source. The agent's own dependencies still come from dependency
/// injection, through the service provider passed to the factory.
/// </para>
/// <para>
/// The lifetime applies to an agent created by a factory:
/// <list type="bullet">
/// <item><description><see cref="ServiceLifetime.Singleton"/>: created on first use from the root service provider, reused for the process, and disposed when this source is disposed at shutdown.</description></item>
/// <item><description><see cref="ServiceLifetime.Scoped"/> and <see cref="ServiceLifetime.Transient"/>: created from the service provider of each response run, and disposed when the lease for that run is disposed. Nothing else can resolve the agent, so the two behave the same.</description></item>
/// </list>
/// An agent passed as an instance is reused for the process and never disposed by this source, because the
/// caller created it.
/// </para>
/// <para>
/// Hosting adds telemetry only to an agent it reuses for every run. An agent created per run must bring its own
/// <see cref="OpenTelemetryAgent"/>, and a workflow agent must also have
/// <see cref="WorkflowAgentExtensions.WithFoundryCheckpointing"/> applied before it, unless
/// <see cref="FoundryResponsesServerOptions.RequireOpenTelemetryAgent"/> is <see langword="false"/>. This source
/// rejects an agent that does not.
/// </para>
/// </remarks>
internal sealed class FoundryHostedAgentSource : IAsyncDisposable, IDisposable
{
    private readonly AIAgent? _instance;
    private readonly Func<IServiceProvider, AIAgent>? _factory;
    private readonly ServiceLifetime _lifetime;
    private readonly IServiceProvider? _rootServices;
    private readonly bool _requireOpenTelemetryAgent;
    private readonly object _gate = new();
    private AIAgent? _singleton;
    private bool _disposed;

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryHostedAgentSource"/> class that serves an agent
    /// instance the caller owns.
    /// </summary>
    /// <param name="agent">The agent to serve.</param>
    internal FoundryHostedAgentSource(AIAgent agent)
    {
        this._instance = Throw.IfNull(agent);
        this._lifetime = ServiceLifetime.Singleton;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryHostedAgentSource"/> class that serves an agent
    /// created by <paramref name="agentFactory"/> with the specified lifetime.
    /// </summary>
    /// <param name="agentFactory">Creates the agent from the service provider it is given.</param>
    /// <param name="lifetime">How long a created agent is reused.</param>
    /// <param name="rootServices">The root service provider, used to create a singleton agent.</param>
    /// <param name="requireOpenTelemetryAgent">
    /// Whether an agent created per run must include an <see cref="OpenTelemetryAgent"/>, as
    /// <see cref="FoundryResponsesServerOptions.RequireOpenTelemetryAgent"/> describes.
    /// </param>
    internal FoundryHostedAgentSource(
        Func<IServiceProvider, AIAgent> agentFactory,
        ServiceLifetime lifetime,
        IServiceProvider rootServices,
        bool requireOpenTelemetryAgent)
    {
        this._factory = Throw.IfNull(agentFactory);
        ValidateLifetime(lifetime);
        this._lifetime = lifetime;
        this._rootServices = Throw.IfNull(rootServices);
        this._requireOpenTelemetryAgent = requireOpenTelemetryAgent;
    }

    /// <summary>
    /// Gets a value indicating whether this source creates a new agent for every run, rather than reusing one
    /// agent for the process.
    /// </summary>
    internal bool CreatesAgentPerRun => this._factory is not null && this._lifetime != ServiceLifetime.Singleton;

    /// <summary>
    /// Gets the agent for one response run or readiness check.
    /// </summary>
    /// <param name="runServices">The service provider of the DI scope owned by the run.</param>
    /// <returns>A lease that disposes the agent when it was created for this run only.</returns>
    /// <exception cref="InvalidOperationException">
    /// The agent created for this run has no <see cref="OpenTelemetryAgent"/> in its pipeline while one is
    /// required. The agent is disposed before this is thrown.
    /// </exception>
    internal async ValueTask<Lease> AcquireAsync(IServiceProvider runServices)
    {
        _ = Throw.IfNull(runServices);

        if (this._instance is not null)
        {
            return new Lease(this._instance, ownsAgent: false);
        }

        if (this._lifetime == ServiceLifetime.Singleton)
        {
            return new Lease(this.GetOrCreateSingleton(), ownsAgent: false);
        }

        AIAgent agent = this.CreateAgent(runServices);
        if (this._requireOpenTelemetryAgent && this.DescribeMissingTelemetry(agent) is { } problem)
        {
            await DisposeAgentAsync(agent).ConfigureAwait(false);
            throw new InvalidOperationException(
                problem +
                " Hosting adds telemetry only to an agent it reuses for every response, because the telemetry of an " +
                "agent created per response has to be disposed with that agent. Set " +
                "FoundryResponsesServerOptions.RequireOpenTelemetryAgent to false to serve the agent without agent telemetry.");
        }

        return new Lease(agent, ownsAgent: true);
    }

    /// <summary>
    /// Describes what an agent created per run is missing to meet the telemetry requirement, or returns
    /// <see langword="null"/> when it meets it.
    /// </summary>
    /// <remarks>
    /// The agent must include an <see cref="OpenTelemetryAgent"/>. A workflow agent must also keep its checkpoints
    /// out of its saved session. Hosting copies a workflow agent so that the copy stores them in Foundry, but it can
    /// copy only the workflow agent itself, not one inside a wrapper such as the <see cref="OpenTelemetryAgent"/>,
    /// so the factory has to call <see cref="WorkflowAgentExtensions.WithFoundryCheckpointing"/> before it
    /// adds the wrapper. A workflow agent built with a checkpoint manager of its own is accepted here, and the
    /// readiness check reports it when it runs in Foundry.
    /// </remarks>
    /// <param name="agent">The agent created for the run.</param>
    private string? DescribeMissingTelemetry(AIAgent agent)
    {
        bool hasTelemetry = agent.GetService<OpenTelemetryAgent>() is not null;
        string factory = $"The agent factory passed to AddFoundryResponses with ServiceLifetime.{this._lifetime}";
        string useOpenTelemetry = $"UseOpenTelemetry(sourceName: \"{ServiceCollectionExtensions.ResponsesSourceName}\")";

        if (agent.GetService<WorkflowAgentMetadata>() is not { } workflow)
        {
            return hasTelemetry
                ? null
                : $"{factory} returned an agent without an OpenTelemetryAgent in its pipeline. Add it in the factory, " +
                  $"for example with agent.AsBuilder().{useOpenTelemetry}.Build().";
        }

        if (!hasTelemetry)
        {
            return $"{factory} returned a workflow agent without an OpenTelemetryAgent in its pipeline. Add it in the " +
                $"factory with agent.WithFoundryCheckpointing(serviceProvider).AsBuilder().{useOpenTelemetry}.Build(). " +
                "WithFoundryCheckpointing must come first, because the checkpoints of a wrapped workflow agent cannot " +
                "be moved to Foundry.";
        }

        return workflow.UsesOwnCheckpointStorage
            ? null
            : $"{factory} returned a workflow agent wrapped before WithFoundryCheckpointing was applied to it, so its " +
              "checkpoints would stay inside its saved session. Call WithFoundryCheckpointing on the workflow agent " +
              $"before adding the OpenTelemetryAgent: agent.WithFoundryCheckpointing(serviceProvider).AsBuilder().{useOpenTelemetry}.Build().";
    }

    /// <summary>
    /// Throws when <paramref name="lifetime"/> is not one of the lifetimes dependency injection defines.
    /// </summary>
    /// <param name="lifetime">The lifetime to check.</param>
    internal static void ValidateLifetime(ServiceLifetime lifetime)
    {
        if (lifetime is not (ServiceLifetime.Singleton or ServiceLifetime.Scoped or ServiceLifetime.Transient))
        {
            Throw.ArgumentOutOfRangeException(nameof(lifetime), lifetime, "Unsupported service lifetime.");
        }
    }

    /// <inheritdoc/>
    public async ValueTask DisposeAsync()
    {
        if (this.TakeSingletonForDisposal() is { } singleton)
        {
            await DisposeAgentAsync(singleton).ConfigureAwait(false);
        }
    }

    /// <inheritdoc/>
    /// <exception cref="InvalidOperationException">
    /// The singleton agent can only be disposed asynchronously, which is also when dependency injection throws
    /// for a service it disposes synchronously.
    /// </exception>
    public void Dispose()
    {
        if (this.TakeSingletonForDisposal() is { } singleton)
        {
            DisposeAgent(singleton);
        }
    }

    private AIAgent GetOrCreateSingleton()
    {
        lock (this._gate)
        {
            ObjectDisposedException.ThrowIf(this._disposed, this);

            // Resolve the DI-managed owner lazily. Its factory resolves the agent's dependencies before DI
            // records the owner for disposal, so the owner disposes the agent while those dependencies are alive.
            if (this._rootServices!.GetService<FoundryHostedSingletonAgentOwner>() is { } owner)
            {
                return owner.Agent;
            }

            // A factory that throws is called again on the next request, as dependency injection does for a
            // singleton, rather than having its failure cached for the life of the process. This fallback is for
            // a source constructed directly rather than through AddFoundryResponses.
            return this._singleton ??= this.CreateAgent(this._rootServices!);
        }
    }

    private AIAgent CreateAgent(IServiceProvider services) =>
        this._factory!(services)
            ?? throw new InvalidOperationException("The agent factory passed to AddFoundryResponses returned null.");

    private AIAgent? TakeSingletonForDisposal()
    {
        lock (this._gate)
        {
            this._disposed = true;
            AIAgent? singleton = this._singleton;
            this._singleton = null;
            return singleton;
        }
    }

    internal static ValueTask DisposeAgentAsync(AIAgent agent) =>
        DisposeAgentAsync(agent, new HashSet<AIAgent>(ReferenceEqualityComparer.Instance));

    private static async ValueTask DisposeAgentAsync(AIAgent agent, HashSet<AIAgent> disposedAgents)
    {
        if (!disposedAgents.Add(agent))
        {
            return;
        }

        OpenTelemetryAgent? telemetryAgent = agent.GetService<OpenTelemetryAgent>();
        AIAgent? telemetryInnerAgent = telemetryAgent?.GetService(typeof(AIAgent), telemetryAgent) as AIAgent;

        switch (agent)
        {
            case IAsyncDisposable asyncDisposable:
                await asyncDisposable.DisposeAsync().ConfigureAwait(false);
                break;
            case IDisposable disposable:
                disposable.Dispose();
                break;
        }

        if (telemetryAgent is not null && !ReferenceEquals(telemetryAgent, agent))
        {
            await DisposeAgentAsync(telemetryAgent, disposedAgents).ConfigureAwait(false);
        }

        if (telemetryInnerAgent is not null)
        {
            await DisposeAgentAsync(telemetryInnerAgent, disposedAgents).ConfigureAwait(false);
        }
    }

    internal static void DisposeAgent(AIAgent agent)
    {
        var disposedAgents = new HashSet<AIAgent>(ReferenceEqualityComparer.Instance);
        DisposeAgent(agent, disposedAgents);
    }

    private static void DisposeAgent(AIAgent agent, HashSet<AIAgent> disposedAgents)
    {
        if (!disposedAgents.Add(agent))
        {
            return;
        }

        OpenTelemetryAgent? telemetryAgent = agent.GetService<OpenTelemetryAgent>();
        AIAgent? telemetryInnerAgent = telemetryAgent?.GetService(typeof(AIAgent), telemetryAgent) as AIAgent;

        switch (agent)
        {
            case IDisposable disposable:
                disposable.Dispose();
                break;
            case IAsyncDisposable asyncDisposable:
                throw new InvalidOperationException(
                    $"'{asyncDisposable.GetType()}' only implements IAsyncDisposable. Use DisposeAsync to dispose the service provider.");
        }

        if (telemetryAgent is not null && !ReferenceEquals(telemetryAgent, agent))
        {
            DisposeAgent(telemetryAgent, disposedAgents);
        }

        if (telemetryInnerAgent is not null)
        {
            DisposeAgent(telemetryInnerAgent, disposedAgents);
        }
    }

    /// <summary>
    /// The agent for one response run or readiness check, disposed with the lease when it was created for
    /// that use only.
    /// </summary>
    internal sealed class Lease : IAsyncDisposable
    {
        private readonly bool _ownsAgent;
        private bool _disposed;

        internal Lease(AIAgent agent, bool ownsAgent)
        {
            this.Agent = agent;
            this._ownsAgent = ownsAgent;
        }

        /// <summary>Gets the agent to serve the run with.</summary>
        internal AIAgent Agent { get; }

        /// <inheritdoc/>
        public ValueTask DisposeAsync()
        {
            if (!this._ownsAgent || this._disposed)
            {
                return default;
            }

            this._disposed = true;
            return DisposeAgentAsync(this.Agent);
        }
    }

    /// <summary>
    /// Owns the singleton agent created by a factory registered with dependency injection.
    /// </summary>
    internal sealed class FoundryHostedSingletonAgentOwner : IAsyncDisposable, IDisposable
    {
        private AIAgent? _agent;

        internal FoundryHostedSingletonAgentOwner(AIAgent agent)
        {
            this._agent = Throw.IfNull(agent);
        }

        internal AIAgent Agent =>
            this._agent ?? throw new ObjectDisposedException(nameof(FoundryHostedSingletonAgentOwner));

        public async ValueTask DisposeAsync()
        {
            if (this.TakeAgent() is { } agent)
            {
                await DisposeAgentAsync(agent).ConfigureAwait(false);
            }
        }

        public void Dispose()
        {
            if (this.TakeAgent() is { } agent)
            {
                DisposeAgent(agent);
            }
        }

        private AIAgent? TakeAgent()
        {
            AIAgent? agent = this._agent;
            this._agent = null;
            return agent;
        }
    }
}
