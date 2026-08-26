// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Moq;
using Valkey.Glide;

namespace Microsoft.Agents.AI.Valkey.UnitTests;

[Collection(nameof(FeatureUsageTestGroup))]
public sealed class FeatureUsageActivationTests : IDisposable
{
    [Fact]
    public async Task InvokingAsync_ActivatesValkeyFeatureAsync()
    {
        // Arrange
        var database = new Mock<IDatabase>();
        database
            .Setup(db => db.ListRangeAsync(It.IsAny<ValkeyKey>(), It.IsAny<long>(), It.IsAny<long>()))
            .ReturnsAsync([]);
        var connection = new Mock<IConnectionMultiplexer>();
        connection.Setup(c => c.GetDatabase()).Returns(database.Object);
        var provider = new ValkeyChatHistoryProvider(
            connection.Object,
            static _ => new ValkeyChatHistoryProvider.State("conversation"));
        FeatureUsageAssert.Reset();

        // Act
        _ = await provider.InvokingAsync(TestHelpers.CreateChatHistoryInvokingContext());

        // Assert
        FeatureUsageAssert.Marked(59);
    }

    public void Dispose() => FeatureUsageAssert.Reset();
}
