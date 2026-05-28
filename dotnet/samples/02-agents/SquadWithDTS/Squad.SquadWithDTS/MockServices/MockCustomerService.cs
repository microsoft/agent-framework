// Copyright (c) Microsoft. All rights reserved.
using Squad.SquadWithDTS.Models;

namespace Squad.SquadWithDTS.MockServices;

internal static class MockCustomerService
{
    private static readonly Dictionary<string, CustomerInfo> Customers = new()
    {
        ["CUST-9921"] = new("CUST-9921", "Enterprise",  "2h",  "alice@acmecorp.example"),
        ["CUST-4201"] = new("CUST-4201", "Business",    "4h",  "bob@widgets.example"),
        ["CUST-0001"] = new("CUST-0001", "Starter",     "24h", "support@startup.example"),
    };

    public static async Task<CustomerInfo> GetCustomerAsync(
        string customerId,
        CancellationToken cancellationToken = default)
    {
        await Task.Delay(80, cancellationToken);
        return Customers.TryGetValue(customerId, out var info)
            ? info
            : new CustomerInfo(customerId, "Unknown", "Best-effort", "support@example.com");
    }
}
