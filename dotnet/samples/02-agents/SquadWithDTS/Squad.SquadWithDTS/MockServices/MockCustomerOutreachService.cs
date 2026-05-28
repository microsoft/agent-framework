// Copyright (c) Microsoft. All rights reserved.
using Squad.SquadWithDTS.Models;

namespace Squad.SquadWithDTS.MockServices;

internal static class MockCustomerOutreachService
{
    public static async Task<string> NotifyCustomerAsync(
        CustomerInfo customer,
        IncidentReport incident,
        CancellationToken cancellationToken = default)
    {
        await Task.Delay(150, cancellationToken);
        return $"Notification sent to {customer.ContactEmail} " +
               $"(tier={customer.Tier}, SLA={customer.Sla}) " +
               $"regarding {incident.IncidentId}";
    }
}
