// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.CosmosNoSql;
using Microsoft.Azure.Cosmos;

namespace Microsoft.Agents.AI.CosmosNoSql.UnitTests;

public sealed class CosmosOptionsHelperTests
{
    [Fact]
    public void CreateOptions_SetsApplicationName_WithComponentAndVersion()
    {
        // Act
        var options = CosmosOptionsHelper.CreateOptions("CosmosChatHistoryProvider");

        // Assert
        Assert.NotNull(options.ApplicationName);
        Assert.StartsWith("Microsoft.Agents.AI.CosmosNoSql.CosmosChatHistoryProvider/", options.ApplicationName);
    }

    [Fact]
    public void CreateOptions_DifferentComponents_ProduceDifferentNames()
    {
        // Act
        var chatOptions = CosmosOptionsHelper.CreateOptions("CosmosChatHistoryProvider");
        var checkpointOptions = CosmosOptionsHelper.CreateOptions("CosmosCheckpointStore");

        // Assert
        Assert.NotEqual(chatOptions.ApplicationName, checkpointOptions.ApplicationName);
        Assert.Contains("CosmosChatHistoryProvider", chatOptions.ApplicationName);
        Assert.Contains("CosmosCheckpointStore", checkpointOptions.ApplicationName);
    }

    [Fact]
    public void CreateOptions_ApplicationName_DoesNotExceedMaxLength()
    {
        // Use a deliberately long component name to trigger truncation
        var longComponent = new string('X', 100);

        // Act
        var options = CosmosOptionsHelper.CreateOptions(longComponent);

        // Assert
        Assert.True(options.ApplicationName!.Length <= 64,
            $"ApplicationName length {options.ApplicationName.Length} exceeds max 64");
    }

    [Fact]
    public void EnsureApplicationName_SetsName_WhenClientHasNone()
    {
        // Arrange
        var clientOptions = new CosmosClientOptions();
        Assert.Null(clientOptions.ApplicationName);

        // Act
        var options = CosmosOptionsHelper.CreateOptions("CosmosChatHistoryProvider");

        // Assert - verify the returned options have ApplicationName set
        Assert.NotNull(options.ApplicationName);
        Assert.NotEmpty(options.ApplicationName);
    }

    [Fact]
    public void CreateOptions_ApplicationName_ContainsVersion()
    {
        // Act
        var options = CosmosOptionsHelper.CreateOptions("CosmosChatHistoryProvider");

        // Assert - should contain a "/" followed by version info
        Assert.Contains("/", options.ApplicationName);
        var parts = options.ApplicationName!.Split('/');
        Assert.Equal(2, parts.Length);
        Assert.False(string.IsNullOrWhiteSpace(parts[1]), "Version portion should not be empty");
    }
}
