// Copyright (c) Microsoft. All rights reserved.

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
        options.DefaultTimeToLive.Should().BeNull();
        options.CancelRemoteTaskOnLocalCancellation.Should().BeTrue();
    }
}
