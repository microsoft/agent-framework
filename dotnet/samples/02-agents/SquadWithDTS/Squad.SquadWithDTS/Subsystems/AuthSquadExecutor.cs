// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Agents.AI.Workflows;
using Squad.SquadWithDTS.Infrastructure;
using Squad.SquadWithDTS.Models;

namespace Squad.SquadWithDTS.Subsystems;

/// <summary>Authentication subsystem squad executor.</summary>
internal sealed class AuthSquadExecutor(ProviderAgentFactory provider)
    : Executor<IncidentWorkflowContext, IncidentWorkflowContext>("AuthSquad")
{
    private const string Charter =
        """
        You are the Authentication incident-response squad. Your charter:
        - Investigate token expiry, clock skew, OIDC provider outages,
          and RBAC policy misconfigurations.
        - Correlate auth failures with deployment or configuration changes.
        - Recommend precise, read-only diagnostic steps.
        Be concise: 3–5 sentences, focus on the most likely auth root cause.
        """;

    public override async ValueTask<IncidentWorkflowContext> HandleAsync(
        IncidentWorkflowContext ctx,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        var analysis = await SubsystemSquadHelpers.RunSubsystemAnalysisAsync(
            provider, "auth-squad", Charter,
            SubsystemSquadHelpers.BuildPrompt("Authentication", ctx), cancellationToken);

        return ctx with { SubsystemAnalysis = analysis };
    }
}
