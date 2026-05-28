// Copyright (c) Microsoft. All rights reserved.
using Squad.SquadWithDTS.Infrastructure;

namespace Squad.SquadWithDTS.Models;

/// <summary>
/// Final report returned after a complete incident-response workflow run.
/// </summary>
internal sealed record IncidentOrchestrationReport(
    string                   Example,
    string                   Status,
    ProviderSummary          Provider,
    IncidentReport           Input,
    string?                  WorkflowRunId,
    IncidentWorkflowContext? FinalContext,
    string                   Runtime
);
