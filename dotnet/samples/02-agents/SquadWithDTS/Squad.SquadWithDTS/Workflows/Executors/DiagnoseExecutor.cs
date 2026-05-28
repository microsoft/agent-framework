// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Squad.SquadWithDTS.Infrastructure;
using Squad.SquadWithDTS.Models;

namespace Squad.SquadWithDTS.Workflows.Executors;

/// <summary>
/// AI diagnosis via Squad: reviews all accumulated context and returns one of:
/// <list type="bullet">
///   <item><c>Resolved</c> — root cause confirmed, incident can be closed.</item>
///   <item><c>NeedsMoreInvestigation</c> — a refined hypothesis is set; the workflow
///         loops back to the <see cref="EnrichExecutor"/> (capped at
///         <see cref="IncidentExample.MaxDiagnosisIterations"/>).</item>
///   <item><c>Inconclusive</c> — insufficient evidence; escalate to senior engineer.</item>
/// </list>
/// </summary>
internal sealed class DiagnoseExecutor(AIAgent squad)
    : Executor<IncidentWorkflowContext, IncidentWorkflowContext>("Diagnose")
{
    public override async ValueTask<IncidentWorkflowContext> HandleAsync(
        IncidentWorkflowContext ctx,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        var prompt = $"""
            You are the incident diagnosis coordinator. Review all accumulated evidence
            and determine whether the root cause is identified.

            Incident: {ctx.Report.Title}
            Subsystem: {ctx.Subsystem}
            Triage hypothesis: {ctx.Hypothesis}

            Enrichment data:
              Customer tier: {ctx.Customer?.Tier} (SLA: {ctx.Customer?.Sla})
              Error rate: {ctx.Metrics?.ErrorRatePercent:0.0}%
              p99 latency: {ctx.Metrics?.P99LatencyMs} ms
              Top errors: {string.Join("; ", ctx.Metrics?.TopErrors ?? [])}
              Recent alerts: {string.Join("; ", ctx.RecentAlerts ?? [])}

            Subsystem analysis: {ctx.SubsystemAnalysis}
            Mitigation steps: {ctx.MitigationSteps}
            External comms: {ctx.ExternalCommsResult}
            Diagnosis iteration: {ctx.DiagnosisIteration + 1} of {IncidentExample.MaxDiagnosisIterations}

            Respond with a JSON object (no markdown fences):
            {{
              "status":              "<Resolved|NeedsMoreInvestigation|Inconclusive>",
              "root_cause":          "<concise root-cause statement>",
              "refined_hypothesis":  "<only if NeedsMoreInvestigation, otherwise null>"
            }}
            """;

        var raw = await DemoRuntime.RunAgentAsync(squad, prompt, cancellationToken);

        var json = System.Text.Json.JsonDocument.Parse(raw).RootElement;

        var status     = json.TryGetProperty("status",             out var s) ? s.GetString() : "Inconclusive";
        var rootCause  = json.TryGetProperty("root_cause",         out var r) ? r.GetString() : raw;
        var refinedHyp = json.TryGetProperty("refined_hypothesis", out var h) && h.ValueKind != System.Text.Json.JsonValueKind.Null
            ? h.GetString()
            : null;

        return ctx with
        {
            DiagnosisStatus    = status,
            RootCause          = rootCause,
            RefinedHypothesis  = refinedHyp,
            DiagnosisIteration = ctx.DiagnosisIteration + 1,
        };
    }
}
