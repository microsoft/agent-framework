// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AIAgentMetadata"/> class.
/// </summary>
public class AIAgentMetadataTests
{
    [Fact]
    public void Constructor_WithNoArguments_SetsProviderNameToNull()
    {
        // Arrange & Act
        AIAgentMetadata metadata = new();

        // Assert
        Assert.Null(metadata.ProviderName);
    }

    [Fact]
    public void Constructor_WithProviderName_SetsProperty()
    {
        // Arrange
        const string ProviderName = "TestProvider";

        // Act
        AIAgentMetadata metadata = new(ProviderName);

        // Assert
        Assert.Equal(ProviderName, metadata.ProviderName);
    }

    [Fact]
    public void Constructor_WithNullProviderName_SetsProviderNameToNull()
    {
        // Arrange & Act
        AIAgentMetadata metadata = new(null);

        // Assert
        Assert.Null(metadata.ProviderName);
    }
}
