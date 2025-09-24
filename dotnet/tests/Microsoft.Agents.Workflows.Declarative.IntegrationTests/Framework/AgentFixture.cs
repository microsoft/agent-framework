// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Shared.IntegrationTests;

namespace Microsoft.Agents.Workflows.Declarative.IntegrationTests.Framework;

public static class AgentFixture
{
    private static IReadOnlyDictionary<string, string?>? s_agentMap;

    internal static async Task<IReadOnlyDictionary<string, string?>> GetAgentsAsync(AzureAIConfiguration config, CancellationToken cancellationToken = default)
    {
        s_agentMap ??= await AgentFactory.CreateAsync("Agents", config, cancellationToken);

        return s_agentMap;
    }
}
