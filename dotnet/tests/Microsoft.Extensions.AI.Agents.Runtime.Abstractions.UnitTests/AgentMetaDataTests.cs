// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents.Runtime.Abstractions.Tests;

public class AgentMetadataTests()
{
    [Fact]
    public void AgentMetadataShouldInitializeCorrectlyTest()
    {
        // Arrange & Act
        AgentMetadata metadata = new("TestType", "TestKey", "TestDescription");

        // Assert
        Assert.Equal("TestType", metadata.Type);
        Assert.Equal("TestKey", metadata.Key);
        Assert.Equal("TestDescription", metadata.Description);
    }
}
