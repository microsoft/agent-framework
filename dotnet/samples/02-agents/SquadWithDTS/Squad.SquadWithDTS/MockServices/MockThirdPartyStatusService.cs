// Copyright (c) Microsoft. All rights reserved.
namespace Squad.SquadWithDTS.MockServices;

internal static class MockThirdPartyStatusService
{
    public static async Task<string> GetStatusPageSummaryAsync(
        CancellationToken cancellationToken = default)
    {
        await Task.Delay(90, cancellationToken);
        return "payment-gateway: DEGRADED (elevated latency us-east-1, since 14:17 UTC) | " +
               "auth-provider: OPERATIONAL | " +
               "cdn: OPERATIONAL";
    }
}
