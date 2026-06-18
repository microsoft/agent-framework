// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

[Trait("Category", "Integration")]
public class AzureAIAgentsChatClientAgentRunTests() : ChatClientAgentRunTests<AzureAIAgentsPersistentFixture>(() => new())
{
}
