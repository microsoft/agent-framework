// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

public class AzureAIAgentsChatClientAgentRunStreamingTests() : ChatClientAgentRunStreamingTests<AzureAIAgentsPersistentFixture>(() => new())
{
}
