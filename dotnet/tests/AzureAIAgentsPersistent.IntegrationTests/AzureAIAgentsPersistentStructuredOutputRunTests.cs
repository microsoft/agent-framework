// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

// Disabled: Azure.AI.Agents.Persistent 1.2.0-beta.9 references McpServerToolApprovalResponseContent
// which was removed in ME.AI 10.4.0. Re-enable once Persistent targets ME.AI 10.4.0+ (expected in 1.2.0-beta.10).
// Tracking: https://github.com/microsoft/agent-framework/issues/4769
[Trait("Category", "IntegrationDisabled")]
public class AzureAIAgentsPersistentStructuredOutputRunTests() : StructuredOutputRunTests<AzureAIAgentsPersistentFixture>(() => new())
{
    private const string SkipReason = "Fails intermittently on the build agent/CI";

    public override Task RunWithResponseFormatReturnsExpectedResultAsync()
    {
        Assert.SkipWhen(SkipReason is not null, SkipReason ?? string.Empty);
        return base.RunWithResponseFormatReturnsExpectedResultAsync();
    }

    public override Task RunWithGenericTypeReturnsExpectedResultAsync()
    {
        Assert.SkipWhen(SkipReason is not null, SkipReason ?? string.Empty);
        return base.RunWithGenericTypeReturnsExpectedResultAsync();
    }

    public override Task RunWithPrimitiveTypeReturnsExpectedResultAsync()
    {
        Assert.SkipWhen(SkipReason is not null, SkipReason ?? string.Empty);
        return base.RunWithPrimitiveTypeReturnsExpectedResultAsync();
    }
}
