// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Mcp.UnitTests;

public class McpTaskOptionsTests
{
    [Fact]
    public void Defaults_AreSane()
    {
        // Act
        McpTaskOptions options = new();

        // Assert
        Assert.True(options.CancelRemoteTaskOnLocalCancellation);
        Assert.Equal(60, options.MaxConsecutiveStuckPolls);
        Assert.Equal(100, options.MaxTotalInputRequests);
        Assert.Equal(TimeSpan.FromSeconds(5), options.RemoteCancellationTimeout);
        Assert.Equal(TimeSpan.FromMilliseconds(10), options.MinimumPollingInterval);
        Assert.Equal(TimeSpan.FromMilliseconds(uint.MaxValue - 1L), options.MaximumPollingInterval);
    }
}
