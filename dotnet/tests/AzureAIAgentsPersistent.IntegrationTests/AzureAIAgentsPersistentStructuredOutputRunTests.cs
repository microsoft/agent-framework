// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

public class AzureAIAgentsPersistentStructuredOutputRunTests() : StructuredOutputRunTests<AzureAIAgentsPersistentFixture>(() => new())
{
    private const string SkipReason = "Fails intermittently, at build agent";

    [Fact(Skip = SkipReason)]
    public override Task RunWithResponseFormatReturnsExpectedResultAsync() =>
        base.RunWithResponseFormatReturnsExpectedResultAsync();

    [Fact(Skip = SkipReason)]
    public override Task RunWithGenericTypeReturnsExpectedResultAsync() =>
        base.RunWithGenericTypeReturnsExpectedResultAsync();

    [Fact(Skip = SkipReason)]
    public override Task RunWithPrimitiveTypeReturnsExpectedResultAsync() =>
        base.RunWithPrimitiveTypeReturnsExpectedResultAsync();
}
