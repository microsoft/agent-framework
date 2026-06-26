// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.Channels.UnitTests;

/// <summary>
/// Covers the channel command contract: a <see cref="ChannelCommand"/> carries a handler that receives a
/// <see cref="ChannelCommandContext"/> (the originating request plus a reply callback), mirroring the Python
/// host's command/handle/reply seam. In v1 the channel self-dispatches; the host does not own a command loop.
/// </summary>
public class ChannelCommandTests
{
    [Fact]
    public async Task Handler_ReceivesContext_AndReplyRoundTripsAsync()
    {
        // Arrange
        var request = new ChannelRequest("probe", "command.invoke", "/reset now");
        ChannelCommandContext? seen = null;
        string? replied = null;

        var command = new ChannelCommand("reset", "Start a fresh session", async ctx =>
        {
            seen = ctx;
            await ctx.Reply($"reset for {ctx.Request.Channel}").ConfigureAwait(false);
        });

        var context = new ChannelCommandContext(request, msg => { replied = msg; return default; });

        // Act - the channel dispatches the matched command
        await command.Handler(context);

        // Assert
        Assert.Same(context, seen);
        Assert.Same(request, seen!.Request);
        Assert.Equal("reset for probe", replied);
    }

    [Fact]
    public void Command_Properties_AreExposed()
    {
        // Arrange / Act
        var command = new ChannelCommand("reset", "Start a fresh session", _ => default);

        // Assert
        Assert.Equal("reset", command.Name);
        Assert.Equal("Start a fresh session", command.Description);
        Assert.NotNull(command.Handler);
    }

    [Fact]
    public void Command_NullName_Throws()
    {
        // Act / Assert
        Assert.Throws<ArgumentNullException>(() => new ChannelCommand(null!, "d", _ => default));
    }

    [Fact]
    public void Command_EmptyName_Throws()
    {
        // Act / Assert
        Assert.Throws<ArgumentException>(() => new ChannelCommand("", "d", _ => default));
    }

    [Fact]
    public void Command_NullDescription_Throws()
    {
        // Act / Assert
        Assert.Throws<ArgumentNullException>(() => new ChannelCommand("reset", null!, _ => default));
    }

    [Fact]
    public void Command_NullHandler_Throws()
    {
        // Act / Assert
        Assert.Throws<ArgumentNullException>(() => new ChannelCommand("reset", "d", null!));
    }

    [Fact]
    public void Context_NullRequest_Throws()
    {
        // Act / Assert
        Assert.Throws<ArgumentNullException>(() => new ChannelCommandContext(null!, _ => default));
    }

    [Fact]
    public void Context_NullReply_Throws()
    {
        // Arrange
        var request = new ChannelRequest("probe", "command.invoke", "/reset");

        // Act / Assert
        Assert.Throws<ArgumentNullException>(() => new ChannelCommandContext(request, null!));
    }
}
