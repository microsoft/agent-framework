// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Declarative.UnitTests;

[Collection(nameof(FeatureUsageTestGroup))]
public sealed class FeatureUsageActivationTests
{
    [Fact]
    public async Task ChatClientPromptAgentFactory_MarksFeatureUsageAsync()
    {
        // Arrange
        var factory = new ChatClientPromptAgentFactory(new Mock<IChatClient>().Object);
        var promptAgent = PromptAgents.CreateTestPromptAgent();
        FeatureUsageAssert.Reset();

        // Act
        _ = await factory.TryCreateAsync(promptAgent);

        // Assert
        FeatureUsageAssert.Marked(65);
    }
}
