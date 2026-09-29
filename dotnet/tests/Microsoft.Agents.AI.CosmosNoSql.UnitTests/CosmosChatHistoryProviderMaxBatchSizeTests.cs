// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.CosmosNoSql.UnitTests;

/// <summary>
/// Tests for <see cref="CosmosChatHistoryProvider.MaxBatchSize"/> validation.
/// These do not need the Cosmos DB Emulator: the client makes no request until the provider reads or writes.
/// </summary>
public sealed class CosmosChatHistoryProviderMaxBatchSizeTests
{
    private const string ConnectionString =
        "AccountEndpoint=https://localhost:8081/;AccountKey=C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw==";

    private static CosmosChatHistoryProvider CreateProvider() =>
        new(ConnectionString, "database", "container", _ => new CosmosChatHistoryProvider.State("conversation"));

    [Fact]
    public void MaxBatchSize_DefaultsToTheCosmosDbLimit()
    {
        // Arrange & Act
        using var provider = CreateProvider();

        // Assert
        Assert.Equal(100, provider.MaxBatchSize);
    }

    [Theory]
    [InlineData(1)]
    [InlineData(50)]
    [InlineData(100)]
    public void MaxBatchSize_WithinRange_IsAccepted(int maxBatchSize)
    {
        // Arrange
        using var provider = CreateProvider();

        // Act
        provider.MaxBatchSize = maxBatchSize;

        // Assert
        Assert.Equal(maxBatchSize, provider.MaxBatchSize);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    [InlineData(101)]
    public void MaxBatchSize_OutOfRange_ThrowsArgumentOutOfRangeException(int maxBatchSize)
    {
        // Arrange
        using var provider = CreateProvider();

        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() => provider.MaxBatchSize = maxBatchSize);
        Assert.Equal(100, provider.MaxBatchSize);
    }
}
