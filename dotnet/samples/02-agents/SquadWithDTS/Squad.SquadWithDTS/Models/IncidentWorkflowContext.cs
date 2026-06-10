// Copyright (c) Microsoft. All rights reserved.
using Squad.SquadWithDTS.Models;

namespace Squad.SquadWithDTS.Models;

/// <summary>
/// Mutable context threaded through every executor in the incident-response workflow.
/// Uses C# record <c>with</c>-expressions so each executor returns an updated snapshot
/// without mutating shared state — safe for DTS checkpointing.
/// </summary>
internal sealed record IncidentWorkflowContext(IncidentReport Report)
{
    // ── set by EnrichExecutor ─────────────────────────────────────────────
    public CustomerInfo?   Customer       { get; init; }
    public MetricsWindow?  Metrics        { get; init; }
    public string[]?       RecentAlerts   { get; init; }

    // ── set by TriageExecutor (Squad AI) ─────────────────────────────────
    public string?  Hypothesis       { get; init; }
    public string?  Subsystem        { get; init; }     // Database | Network | Authentication | Payments
    public string?  TriageSeverity   { get; init; }
    public string[]? RequiredEvidence { get; init; }

    // ── set by ExternalCommsExecutor ─────────────────────────────────────
    public string? ExternalCommsResult { get; init; }

    // ── set by subsystem-squad executors ────────────────────────────────
    public string? SubsystemAnalysis { get; init; }

    // ── set by MitigateExecutor ──────────────────────────────────────────
    public string? MitigationSteps { get; init; }

    // ── set by DiagnoseExecutor (Squad AI) ───────────────────────────────
    public string? RootCause           { get; init; }
    public string? DiagnosisStatus     { get; init; }   // Resolved | NeedsMoreInvestigation | Inconclusive
    public string? RefinedHypothesis   { get; init; }
    public int     DiagnosisIteration  { get; init; }
}
