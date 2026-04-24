// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

[Trait("Category", "Integration")]
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
