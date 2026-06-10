// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Agents.AI.Workflows;
using Squad.SquadWithDTS.Infrastructure;
using Squad.SquadWithDTS.Models;

namespace Squad.SquadWithDTS.Subsystems;

/// <summary>Database subsystem squad executor.</summary>
internal sealed class DatabaseSquadExecutor(ProviderAgentFactory provider)
    : Executor<IncidentWorkflowContext, IncidentWorkflowContext>("DatabaseSquad")
{
    private const string Charter =
        """
        You are the Database incident-response squad. Your charter:
        - Investigate connection pool exhaustion, lock contention, slow queries,
          and index fragmentation.
        - Correlate database metrics with application error patterns.
        - Recommend precise, read-only diagnostic steps (no schema changes).
        Be concise: 3–5 sentences, focus on the most likely database root cause.
        """;

    public override async ValueTask<IncidentWorkflowContext> HandleAsync(
        IncidentWorkflowContext ctx,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        var analysis = await SubsystemSquadHelpers.RunSubsystemAnalysisAsync(
            provider, "database-squad", Charter,
            SubsystemSquadHelpers.BuildPrompt("Database", ctx), cancellationToken);

        return ctx with { SubsystemAnalysis = analysis };
    }
}
