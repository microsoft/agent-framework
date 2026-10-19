// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// An <see cref="IAgentHandler"/> that resolves the agent and its session services from a new service scope
/// for each A2A operation, so the configured DI lifetimes of the hosted registration are honored.
/// </summary>
/// <remarks>
/// A2A operations can continue in the background after the originating HTTP request completes, so each
/// operation owns its scope instead of borrowing the request scope.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
internal sealed class ScopedA2AAgentHandler : IAgentHandler
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly string _agentName;
    private readonly AIAgent? _agent;
    private readonly string? _sessionStorageIdentity;
    private readonly AgentRunMode _runMode;

    /// <summary>
    /// Initializes a new instance of the <see cref="ScopedA2AAgentHandler"/> class.
    /// </summary>
    /// <param name="scopeFactory">The factory used to create a scope for each operation.</param>
    /// <param name="agentName">The name that keys the agent registration and its hosted services.</param>
    /// <param name="agent">A fixed agent instance, or <see langword="null"/> to resolve the keyed registration in each scope.</param>
    /// <param name="sessionStorageIdentity">
    /// The stable logical identity that partitions persisted sessions, or <see langword="null"/> to use the agent instance identity.
    /// </param>
    /// <param name="runMode">Controls which A2A artifact the agent response is returned as.</param>
    public ScopedA2AAgentHandler(IServiceScopeFactory scopeFactory, string agentName, AIAgent? agent, string? sessionStorageIdentity, AgentRunMode runMode)
    {
        this._scopeFactory = scopeFactory;
        this._agentName = agentName;
        this._agent = agent;
        this._sessionStorageIdentity = sessionStorageIdentity;
        this._runMode = runMode;
    }

    /// <inheritdoc/>
    public async Task ExecuteAsync(RequestContext context, AgentEventQueue eventQueue, CancellationToken cancellationToken)
    {
        AsyncServiceScope scope = this._scopeFactory.CreateAsyncScope();
        await using (scope.ConfigureAwait(false))
        {
            await this.CreateHandler(scope.ServiceProvider).ExecuteAsync(context, eventQueue, cancellationToken).ConfigureAwait(false);
        }
    }

    /// <inheritdoc/>
    public async Task CancelAsync(RequestContext context, AgentEventQueue eventQueue, CancellationToken cancellationToken)
    {
        AsyncServiceScope scope = this._scopeFactory.CreateAsyncScope();
        await using (scope.ConfigureAwait(false))
        {
            // Canceling a task does not involve the agent, so only a custom handler needs to be resolved.
            Task cancellation = scope.ServiceProvider.GetKeyedService<IAgentHandler>(this._agentName) is { } agentHandler
                ? agentHandler.CancelAsync(context, eventQueue, cancellationToken)
                : A2AAgentHandler.CancelTaskAsync(context, eventQueue, cancellationToken);
            await cancellation.ConfigureAwait(false);
        }
    }

    private IAgentHandler CreateHandler(IServiceProvider services)
    {
        if (services.GetKeyedService<IAgentHandler>(this._agentName) is { } agentHandler)
        {
            return agentHandler;
        }

        AIAgent agent = this._agent ?? services.GetRequiredKeyedService<AIAgent>(this._agentName);
        AIHostAgent hostAgent = A2AServerServiceCollectionExtensions.CreateHostAgent(services, agent, this._agentName, this._sessionStorageIdentity);
        return new A2AAgentHandler(hostAgent, this._runMode);
    }
}
