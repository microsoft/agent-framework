// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;
#pragma warning disable SYSLIB1006 // Preserve the legacy EventId 0 for every migrated log message.

/// <summary>
/// Reports, on the <c>GET /readiness</c> probe, a hosted agent configured to have its own service
/// store the responses it produces, so a container that would record the conversation twice is caught
/// before it takes any traffic.
/// </summary>
/// <remarks>
/// <para>
/// The agent the container serves is run for real, with its chat client replaced for that run by
/// <see cref="StoredOutputProbeChatClient"/>, which answers without calling anything. The run therefore
/// builds the very request the agent would have sent, and the probe reads the store setting off it.
/// Nothing hosting adds per request is applied here, so what the probe sees is how the container
/// configured its agent. Nothing leaves the container either.
/// </para>
/// <para>
/// Only a confirmed "this asks to be stored" fails the probe. An agent that is not a
/// <see cref="ChatClientAgent"/>, a request that carries no such setting, and a run that could not be
/// completed are all reported as healthy: this package cannot tell what those would do, and a
/// readiness probe is the wrong place to turn an uncertainty into an outage.
/// </para>
/// </remarks>
internal sealed partial class HostedStoredOutputHealthCheck : IHealthCheck
{
    private readonly IServiceProvider _serviceProvider;
    private readonly FoundryHostedAgentSource _agentSource;
    private readonly FoundryResponsesServerOptions _options;
    private readonly ILogger<HostedStoredOutputHealthCheck>? _logger;

    public HostedStoredOutputHealthCheck(
        IServiceProvider serviceProvider,
        FoundryHostedAgentSource agentSource,
        FoundryResponsesServerOptions hostingOptions,
        ILogger<HostedStoredOutputHealthCheck>? logger = null)
    {
        _ = Throw.IfNull(serviceProvider);
        _ = Throw.IfNull(agentSource);
        _ = Throw.IfNull(hostingOptions);

        this._serviceProvider = serviceProvider;
        this._agentSource = agentSource;
        this._options = hostingOptions;
        this._logger = logger;
    }

    public async Task<HealthCheckResult> CheckHealthAsync(HealthCheckContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        List<string> storingAgents = [];
        var checkedAgents = 0;

        // A scoped or transient agent is created from a scope that is disposed once the check is done, the
        // same way the response handler gets it per run.
        AsyncServiceScope serviceScope = this._serviceProvider.CreateAsyncScope();
        await using (serviceScope.ConfigureAwait(false))
        {
            FoundryHostedAgentSource.Lease agentLease = await this._agentSource.AcquireAsync(serviceScope.ServiceProvider).ConfigureAwait(false);
            await using (agentLease.ConfigureAwait(false))
            {
                if (this._options.InferenceStoredOutputAllowed)
                {
                    return HealthCheckResult.Healthy(
                        "The hosted agent backend storage usage was detected and inference stored output is explicitly allowed.");
                }

                AIAgent agent = agentLease.Agent;

                // Hosting only reaches the store setting through ChatClientAgent's chat options, so any
                // other agent runs untouched and there is nothing to report.
                if (agent.GetService<ChatClientAgent>() is not null)
                {
                    checkedAgents++;
                    if (await this.StoresItsOwnResponsesAsync(agent, cancellationToken).ConfigureAwait(false))
                    {
                        storingAgents.Add(agent.Name ?? agent.Id);
                    }
                }
            }
        }

        if (storingAgents.Count > 0)
        {
            return new HealthCheckResult(
                status: context.Registration.FailureStatus,
                description: string.Create(
                    CultureInfo.InvariantCulture,
                    $"Stored output: {storingAgents.Count} registered agent(s) should not have server side storage enabled. This will produce a new untracked conversation/response in the server while the hosted agent will also generate a conversation for the request of the agent. This setting is only allowed when enabling the FoundryResponsesServerOptions.InferenceStoredOutputAllowed flag, which leaves the agent's own storage setting untouched and keeps that second recording on purpose."),
                data: new Dictionary<string, object>(StringComparer.Ordinal) { ["storingAgents"] = storingAgents });
        }

        return HealthCheckResult.Healthy(
            string.Create(CultureInfo.InvariantCulture, $"Stored output: {checkedAgents} agent(s) checked, none asking to store responses of their own."));
    }

    /// <summary>
    /// Runs a stand-in built from the agent's own configuration, with its chat client replaced by one
    /// that calls nothing, and reports whether the request that configuration produces asks for the
    /// response to be stored.
    /// </summary>
    /// <remarks>
    /// The run carries no chat options of its own, so the agent's own configuration is what reaches the
    /// probe. Overriding the setting here, the way the request handler does per turn, would only show
    /// the override back.
    /// <para>
    /// A stand-in is built rather than running the hosted agent because that agent's chat history
    /// provider and context providers would run with it. Those are the parts most likely to reach
    /// outside the container, a memory or search provider for instance, and to write state: a readiness
    /// probe would then make external calls and add its own empty turn to real conversations, on every
    /// probe, for a run that asks the agent nothing. The stand-in keeps everything that decides the
    /// stored output setting, the chat options and the raw request factory among them, and drops both
    /// kinds of provider, so the probe stays free of side effects.
    /// </para>
    /// Wrappers are not run by readiness because their middleware may have side effects. Middleware
    /// that changes the effective run options therefore remains unknown and does not fail readiness.
    /// The request handler performs the authoritative post-run check and rejects any turn that
    /// unexpectedly produced a downstream conversation id.
    /// </remarks>
    private async Task<bool> StoresItsOwnResponsesAsync(AIAgent agent, CancellationToken cancellationToken)
    {
        var probe = new StoredOutputProbeChatClient();
        var probeOptions = agent.GetService<ChatClientAgentOptions>()?.Clone() ?? new ChatClientAgentOptions();
        probeOptions.ChatHistoryProvider = null;
        probeOptions.AIContextProviders = null;

        try
        {
            var probeAgent = new ChatClientAgent(probe, probeOptions);
            await probeAgent.RunAsync([], cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is not OperationCanceledException || !cancellationToken.IsCancellationRequested)
        {
            // The agent could not complete a run it was never really asked to answer, which says nothing
            // about how it stores responses and is not held against it. A cancellation of its own, a
            // timeout inside the agent for instance, lands here too; only the health check's own
            // cancellation is left to propagate.
            if (this._logger is { } logger)
            {
                LogStoredOutputProbeFailed(logger, agent.Name, ex);
            }

            return false;
        }

        if (probe.StoredOutputEnabled is null)
        {
            if (this._logger is { } logger)
            {
                LogStoredOutputSettingUnknown(logger, agent.Name);
            }
        }

        return probe.StoredOutputEnabled is true;
    }

    [LoggerMessage(LogLevel.Debug, "Could not probe the stored output setting for agent '{AgentName}'.", EventId = 0)]
    private static partial void LogStoredOutputProbeFailed(
        ILogger logger,
        string? agentName,
        Exception exception);
    [LoggerMessage(LogLevel.Debug, "Agent '{AgentName}' builds a request whose stored output setting could not be determined.", EventId = 0)]
    private static partial void LogStoredOutputSettingUnknown(ILogger logger, string? agentName);
}
