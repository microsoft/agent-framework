// Copyright (c) Microsoft. All rights reserved.
using Squad.SquadWithDTS.Models;

namespace Squad.SquadWithDTS.MockServices;

internal static class MockMetricsService
{
    public static async Task<MetricsWindow> GetMetricsWindowAsync(
        string region,
        CancellationToken cancellationToken = default)
    {
        await Task.Delay(120, cancellationToken);
        return new MetricsWindow(
            ErrorRatePercent: 14.3,
            P99LatencyMs: 8_240,
            RequestsPerMinute: 3_150,
            TopErrors:
            [
                "ConnectionPoolExhausted: checkout-db pool max=50 active=50 waiting=91",
                "TimeoutException: payment-gateway /charge timeout after 5000ms",
                "SqlException: deadlock on orders table index ix_orders_customer"
            ]);
    }
}
