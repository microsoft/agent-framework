// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Squad.SquadWithDTS.Infrastructure;
using Squad.SquadWithDTS.Models;

namespace Squad.SquadWithDTS.Workflows.Executors;

/// <summary>
/// AI triage via Squad: determines severity, subsystem, initial hypothesis,
/// and the evidence required by downstream executors.
/// </summary>
internal sealed class TriageExecutor(AIAgent squad)
    : Executor<IncidentWorkflowContext, IncidentWorkflowContext>("Triage")
{
    public override async ValueTask<IncidentWorkflowContext> HandleAsync(
        IncidentWorkflowContext ctx,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        var prompt = $"""
            You are the on-call incident triage coordinator.

            Incident: {ctx.Report.Title}
            Service:  {ctx.Report.AffectedService}
            Region:   {ctx.Report.Region}
            Severity: {ctx.Report.Severity}

            Description:
            {ctx.Report.InitialDescription}

            Respond with a JSON object (no markdown fences) with exactly these fields:
            {{
              "severity":          "<P1|P2|P3>",
              "subsystem":         "<Database|Network|Authentication|Payments>",
              "hypothesis":        "<one-sentence root-cause hypothesis>",
              "required_evidence": ["<evidence item 1>", "<evidence item 2>", ...]
            }}
            """;

        var raw = await DemoRuntime.RunAgentAsync(squad, prompt, cancellationToken);

        // Parse the JSON response (Squad always returns valid JSON for structured prompts)
        var json = System.Text.Json.JsonDocument.Parse(raw).RootElement;

        return ctx with
        {
            TriageSeverity   = json.TryGetProperty("severity",   out var sev)  ? sev.GetString()  : ctx.Report.Severity,
            Subsystem        = json.TryGetProperty("subsystem",  out var sub)  ? sub.GetString()  : "Database",
            Hypothesis       = json.TryGetProperty("hypothesis", out var hyp)  ? hyp.GetString()  : raw,
            RequiredEvidence = json.TryGetProperty("required_evidence", out var evArr)
                ? evArr.EnumerateArray().Select(e => e.GetString() ?? "").ToArray()
                : [],
        };
    }
}
