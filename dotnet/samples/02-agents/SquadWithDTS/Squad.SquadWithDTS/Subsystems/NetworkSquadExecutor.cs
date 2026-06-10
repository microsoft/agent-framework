// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Agents.AI.Workflows;
using Squad.SquadWithDTS.Infrastructure;
using Squad.SquadWithDTS.Models;

namespace Squad.SquadWithDTS.Subsystems;

/// <summary>Network subsystem squad executor.</summary>
internal sealed class NetworkSquadExecutor(ProviderAgentFactory provider)
    : Executor<IncidentWorkflowContext, IncidentWorkflowContext>("NetworkSquad")
{
    private const string Charter =
        """
        You are the Network incident-response squad. Your charter:
        - Investigate DNS failures, load-balancer health, latency spikes,
          and packet loss between service mesh nodes.
        - Correlate network events with service error patterns.
        - Recommend precise, read-only diagnostic steps.
        Be concise: 3–5 sentences, focus on the most likely network root cause.
        """;

    public override async ValueTask<IncidentWorkflowContext> HandleAsync(
        IncidentWorkflowContext ctx,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        var analysis = await SubsystemSquadHelpers.RunSubsystemAnalysisAsync(
            provider, "network-squad", Charter,
            SubsystemSquadHelpers.BuildPrompt("Network", ctx), cancellationToken);

        return ctx with { SubsystemAnalysis = analysis };
    }
}
