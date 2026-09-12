// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Unit tests for <see cref="AgentSessionStoreKey"/>.
/// </summary>
public sealed class AgentSessionStoreKeyTests
{
    [Fact]
    public void Constructor_CopiesAndSortsPartitions()
    {
        // Arrange
        var partitions = new Dictionary<string, string>
        {
            ["user"] = "user-1",
            ["tenant"] = "tenant-1",
        };

        // Act
        var key = new AgentSessionStoreKey("session-1", partitions);
        partitions["user"] = "changed";

        // Assert
        Assert.Equal("session-1", key.SessionId);
        Assert.Equal(["tenant", "user"], key.Partitions.Keys);
        Assert.Equal("user-1", key.Partitions["user"]);
    }

    [Fact]
    public void Equality_IgnoresPartitionInsertionOrder()
    {
        // Arrange
        var first = new AgentSessionStoreKey(
            "session-1",
            new Dictionary<string, string>
            {
                ["tenant"] = "tenant-1",
                ["user"] = "user-1",
            });
        var second = new AgentSessionStoreKey(
            "session-1",
            new Dictionary<string, string>
            {
                ["user"] = "user-1",
                ["tenant"] = "tenant-1",
            });

        // Act and assert
        Assert.Equal(first, second);
        Assert.Equal(first.GetHashCode(), second.GetHashCode());
    }

    [Fact]
    public void Equality_DistinguishesPartitionNamesValuesAndMissingPartitions()
    {
        // Arrange
        var unpartitioned = new AgentSessionStoreKey("tenant::session");
        var tenantPartition = new AgentSessionStoreKey("session").WithPartition("tenant", "tenant");
        var userPartition = new AgentSessionStoreKey("session").WithPartition("user", "tenant");

        // Act and assert
        Assert.NotEqual(unpartitioned, tenantPartition);
        Assert.NotEqual(tenantPartition, userPartition);
    }

    [Fact]
    public void WithPartition_ReturnsNewKeyAndPreservesOriginal()
    {
        // Arrange
        var original = new AgentSessionStoreKey("session-1");

        // Act
        AgentSessionStoreKey partitioned = original.WithPartition("tenant", "tenant-1");

        // Assert
        Assert.Empty(original.Partitions);
        Assert.Equal("tenant-1", partitioned.Partitions["tenant"]);
    }

    [Fact]
    public void WithPartition_SameValue_ReturnsSameInstance()
    {
        // Arrange
        var key = new AgentSessionStoreKey("session-1").WithPartition("tenant", "tenant-1");

        // Act
        AgentSessionStoreKey result = key.WithPartition("tenant", "tenant-1");

        // Assert
        Assert.Same(key, result);
    }

    [Theory]
    [InlineData("")]
    [InlineData(" ")]
    public void Constructor_BlankSessionId_Throws(string sessionId)
    {
        // Act and assert
        Assert.Throws<ArgumentException>(() => new AgentSessionStoreKey(sessionId));
    }

    [Theory]
    [InlineData("", "value")]
    [InlineData(" ", "value")]
    [InlineData("name", "")]
    [InlineData("name", " ")]
    public void Constructor_BlankPartition_Throws(string name, string value)
    {
        // Act and assert
        Assert.Throws<ArgumentException>(
            () => new AgentSessionStoreKey(
                "session-1",
                new Dictionary<string, string> { [name] = value }));
    }
}
