// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public sealed class FoundryResponsesServerOptionsTests
{
    [Fact]
    public void Constructor_UsesAgentServerDefaults()
    {
        // Arrange
        var options = new FoundryResponsesServerOptions();

        // Act + Assert
        Assert.False(options.ResilientBackground);
        Assert.False(options.SteerableConversations);
    }
}
