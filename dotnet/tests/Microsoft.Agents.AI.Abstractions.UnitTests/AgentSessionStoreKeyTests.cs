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
    public void Constructor_WithoutPartitions_LeavesPartitionsNull()
    {
        // Act
        var omitted = new AgentSessionStoreKey("session-1");
        var explicitNull = new AgentSessionStoreKey("session-1", partitions: null);
        var empty = new AgentSessionStoreKey("session-1", new Dictionary<string, string>());

        // Assert
        Assert.Null(omitted.Partitions);
        Assert.Null(explicitNull.Partitions);
        Assert.Null(empty.Partitions);
        Assert.Equal(omitted, explicitNull);
        Assert.Equal(explicitNull, empty);
        Assert.Equal(empty, omitted);
        Assert.Equal(omitted.GetHashCode(), explicitNull.GetHashCode());
        Assert.Equal(omitted.GetHashCode(), empty.GetHashCode());
    }

    [Fact]
    public void Equality_NullPartitions_DistinguishesSessionAndPartitionedKeys()
    {
        // Arrange
        var key = new AgentSessionStoreKey("session-1", partitions: null);
        var otherSession = new AgentSessionStoreKey("session-2", partitions: null);
        var partitioned = key.WithPartition("user", "alice");

        // Act and assert
        Assert.False(key.Equals(otherSession));
        Assert.False(key.Equals(partitioned));
        Assert.False(partitioned.Equals(key));
        Assert.False(key.Equals(null));
    }

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
        Assert.NotNull(key.Partitions);
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
        Assert.Null(original.Partitions);
        Assert.NotNull(partitioned.Partitions);
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
