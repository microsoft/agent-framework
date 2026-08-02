// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Azure.Functions.Worker;
using Microsoft.DurableTask;

namespace HostedAgent;

public static class DurableTriggerDiscovery
{
    [Function(nameof(DurableTriggerDiscovery))]
    public static Task RunAsync([OrchestrationTrigger] TaskOrchestrationContext context)
    {
        // The isolated worker SDK indexes Durable triggers from the app assembly.
        // Hosting-only apps still need one local orchestrator for discovery.
        return Task.CompletedTask;
    }
}
