// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Internal;

namespace Microsoft.Agents.AI.Foundry;

internal static class FoundryUserAgentPolicies
{
    internal static AgentFrameworkUserAgentPolicyRegistration Registration { get; } =
        new(
            [
                "services.ai.azure.com",
                "inference.ai.azure.com",
            ],
            BaseUserAgentScope.AllRequests);
}
