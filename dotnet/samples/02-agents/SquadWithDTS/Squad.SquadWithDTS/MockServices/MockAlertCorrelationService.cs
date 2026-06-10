// Copyright (c) Microsoft. All rights reserved.
namespace Squad.SquadWithDTS.MockServices;

internal static class MockAlertCorrelationService
{
    public static async Task<string[]> GetRecentAlertsAsync(
        string region,
        CancellationToken cancellationToken = default)
    {
        await Task.Delay(60, cancellationToken);
        return
        [
            "ALERT-7781 checkout-db connection saturation (fired 14:22 UTC)",
            "ALERT-7782 payment-gateway external latency elevated (fired 14:19 UTC)",
            "ALERT-7783 orders table lock contention > 500 ms (fired 14:23 UTC)"
        ];
    }
}
