// Copyright (c) Microsoft. All rights reserved.

using System;
using FluentAssertions;

namespace Microsoft.Agents.AI.Mcp.UnitTests;

public class McpTaskOptionsTests
{
    [Fact]
    public void Defaults_AreSane()
    {
        // Act
        McpTaskOptions options = new();

        // Assert
        options.CancelRemoteTaskOnLocalCancellation.Should().BeTrue();
        options.MaxConsecutiveStuckPolls.Should().Be(60);
        options.MaxTotalInputRequests.Should().Be(100);
        options.RemoteCancellationTimeout.Should().Be(TimeSpan.FromSeconds(5));
        options.MinimumPollingInterval.Should().Be(TimeSpan.FromMilliseconds(10));
        options.MaximumPollingInterval.Should().Be(TimeSpan.FromMilliseconds(uint.MaxValue - 1L));
    }
}
