// Copyright (c) Microsoft. All rights reserved.
namespace Squad.SquadWithDTS.Models;

/// <summary>
/// Aggregated metrics window for the affected service, fetched during deterministic enrichment.
/// </summary>
internal sealed record MetricsWindow(
    double   ErrorRatePercent,
    int      P99LatencyMs,
    int      RequestsPerMinute,
    string[] TopErrors
);
