// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Agents.AI.Workflows;
using Squad.SquadWithDTS.Infrastructure;
using Squad.SquadWithDTS.Models;

namespace Squad.SquadWithDTS.Subsystems;

/// <summary>Payments subsystem squad executor.</summary>
internal sealed class PaymentsSquadExecutor(ProviderAgentFactory provider)
    : Executor<IncidentWorkflowContext, IncidentWorkflowContext>("PaymentsSquad")
{
    private const string Charter =
        """
        You are the Payments incident-response squad. Your charter:
        - Investigate payment gateway timeouts, idempotency failures,
          retry-queue saturation, and PCI compliance anomalies.
        - Correlate payment errors with third-party provider status.
        - Recommend precise, read-only diagnostic steps.
        Be concise: 3–5 sentences, focus on the most likely payments root cause.
        """;

    public override async ValueTask<IncidentWorkflowContext> HandleAsync(
        IncidentWorkflowContext ctx,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        var analysis = await SubsystemSquadHelpers.RunSubsystemAnalysisAsync(
            provider, "payments-squad", Charter,
            SubsystemSquadHelpers.BuildPrompt("Payments", ctx), cancellationToken);

        return ctx with { SubsystemAnalysis = analysis };
    }
}
