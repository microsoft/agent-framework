// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using AgentConformance.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

public class AzureAIAgentsPersistentStructuredOutputRunTests() : StructuredOutputRunTests<AzureAIAgentsPersistentFixture>(() => new())
{
    [Fact(Skip = "Fails intermittently, at build agent")]
    public override Task RunWithResponseFormatReturnsExpectedResultAsync() =>
    base.RunWithResponseFormatReturnsExpectedResultAsync();
}
