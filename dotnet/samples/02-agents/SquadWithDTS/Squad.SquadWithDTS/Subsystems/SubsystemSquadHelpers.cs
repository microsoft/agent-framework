// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Agents.AI.Workflows;
using Squad.SquadWithDTS.Infrastructure;
using Squad.SquadWithDTS.Models;

namespace Squad.SquadWithDTS.Subsystems;

/// <summary>
/// Shared helpers used by all subsystem squad executors.
/// </summary>
internal static class SubsystemSquadHelpers
{
    internal static async Task<string> RunSubsystemAnalysisAsync(
        ProviderAgentFactory provider,
        string agentName,
        string charter,
        string prompt,
        CancellationToken ct)
    {
        if (!provider.Summary.IsProviderBacked)
        {
            // Demo fallback when no LLM provider is configured.
            return $"[{agentName}] Provider not configured — returning deterministic fallback. " +
                   $"Based on the context, the most likely root cause is connection pool exhaustion " +
                   $"combined with external gateway latency. Recommend: check pool metrics, inspect " +
                   $"slow-query log, verify third-party status page.";
        }

        await using var agent = provider.CreateAgent(agentName, charter).Scope;
        var (aiAgent, _) = provider.CreateAgent(agentName, charter);
        return await DemoRuntime.RunAgentAsync(aiAgent, prompt, ct);
    }

    internal static string BuildPrompt(string subsystem, IncidentWorkflowContext ctx) => $$"""
        Incident assigned to {{subsystem}} squad.

        Title:    {{ctx.Report.Title}}
        Region:   {{ctx.Report.Region}}
        Customer: {{ctx.Customer?.Tier ?? "Unknown"}} (SLA {{ctx.Customer?.Sla ?? "unknown"}})

        Triage hypothesis:  {{ctx.Hypothesis ?? "(none)"}}
        Required evidence:  {{FormatArray(ctx.RequiredEvidence)}}

        Metrics:
          Error rate:       {{ctx.Metrics?.ErrorRatePercent:0.0}}%
          p99 latency:      {{ctx.Metrics?.P99LatencyMs:0}} ms
          Requests/min:     {{ctx.Metrics?.RequestsPerMinute}}
          Top errors:       {{FormatArray(ctx.Metrics?.TopErrors)}}

        Recent alerts:       {{FormatArray(ctx.RecentAlerts)}}
        External comms:      {{ctx.ExternalCommsResult ?? "(none)"}}

        Provide your subsystem-specific diagnosis and top 3 read-only investigative steps.
        """;

    private static string FormatArray(string[]? items) =>
        items is null or { Length: 0 }
            ? "(none)"
            : string.Join("; ", items);
}
