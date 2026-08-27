// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Internal;

namespace Microsoft.Agents.AI.OpenAI;

internal static class OpenAIUserAgentPolicies
{
    internal static AgentFrameworkUserAgentPolicyRegistration Registration { get; } =
        new(
            [
                "cognitiveservices.azure.com",
                "openai.azure.com",
                "services.ai.azure.com",
            ],
            BaseUserAgentScope.ApprovedOrigins);
}
