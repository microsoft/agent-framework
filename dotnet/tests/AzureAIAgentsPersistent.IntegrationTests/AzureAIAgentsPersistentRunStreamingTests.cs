// Copyright (c) Microsoft. All rights reserved.

using AgentConformance.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

// Disabled: Azure.AI.Agents.Persistent 1.2.0-beta.9 references McpServerToolApprovalResponseContent
// which was removed in ME.AI 10.4.0. Re-enable once Persistent targets ME.AI 10.4.0+ (expected in 1.2.0-beta.10).
// Tracking: https://github.com/microsoft/agent-framework/issues/4769
[Trait("Category", "IntegrationDisabled")]
public class AzureAIAgentsPersistentRunStreamingTests() : RunStreamingTests<AzureAIAgentsPersistentFixture>(() => new())
{
}
