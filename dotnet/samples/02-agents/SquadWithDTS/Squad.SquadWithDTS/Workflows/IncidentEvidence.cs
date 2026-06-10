// Copyright (c) Microsoft. All rights reserved.
using Squad.SquadWithDTS.Models;

namespace Squad.SquadWithDTS.Workflows;

/// <summary>
/// Synthetic incident test data used when running the demo without a real alert feed.
/// </summary>
internal static class IncidentEvidence
{
    public static IncidentReport CreateSyntheticIncidentReport() => new(
        IncidentId:          "INC-20260520-0042",
        Title:               "Checkout service degraded — connection pool exhaustion + payment gateway timeouts",
        Severity:            "P1",
        Region:              "us-east-1",
        CustomerId:          "CUST-9921",
        AffectedService:     "checkout-service",
        InitialDescription:  """
            Multiple customers reporting checkout failures since 14:19 UTC.
            Payment-gateway timeouts spiking to 8 s (p99). DB connection pool
            saturated: active=50/50, waiting=91. Deadlock errors on orders table.
            Correlated with a deployment of checkout-service v2.14.1 at 14:05 UTC.
            SRE pager fired at 14:22 UTC after 14% error-rate threshold exceeded.
            """
    );
}
