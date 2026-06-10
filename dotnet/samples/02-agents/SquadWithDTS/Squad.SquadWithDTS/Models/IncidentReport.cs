// Copyright (c) Microsoft. All rights reserved.
namespace Squad.SquadWithDTS.Models;

/// <summary>
/// Represents the raw incident alert that triggers the workflow.
/// </summary>
internal sealed record IncidentReport(
    string IncidentId,
    string Title,
    string Severity,
    string Region,
    string CustomerId,
    string AffectedService,
    string InitialDescription
);
