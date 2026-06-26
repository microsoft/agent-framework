// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests;

/// <summary>
/// Direct coverage of <see cref="AIAgentRunner"/> session-mode handling, including the ADR-0027
/// <see cref="SessionMode.Required"/> contract that a usable session key must be present.
/// </summary>
public class AIAgentRunnerTests
{
    [Fact]
    public async Task SessionModeRequired_WithoutKey_ThrowsAsync()
    {
        // Arrange
        var runner = new AIAgentRunner(new EchoAgent(), new InMemoryHostStateStore());
        var request = new ChannelRequest("responses", "message.create", "hi") { SessionMode = SessionMode.Required };

        // Act / Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await runner.RunAsync(request, default));
    }

    [Fact]
    public async Task SessionModeRequired_WithKey_RunsAsync()
    {
        // Arrange
        var runner = new AIAgentRunner(new EchoAgent(), new InMemoryHostStateStore());
        var request = new ChannelRequest("responses", "message.create", "hi")
        {
            SessionMode = SessionMode.Required,
            Session = new ChannelSession { IsolationKey = "alice" },
        };

        // Act
        var result = await runner.RunAsync(request, default);

        // Assert
        Assert.NotNull(result.ResultObject);
    }

    [Fact]
    public async Task SessionModeDisabled_WithoutKey_RunsAsync()
    {
        // Arrange
        var runner = new AIAgentRunner(new EchoAgent(), new InMemoryHostStateStore());
        var request = new ChannelRequest("responses", "message.create", "hi") { SessionMode = SessionMode.Disabled };

        // Act
        var result = await runner.RunAsync(request, default);

        // Assert
        Assert.NotNull(result.ResultObject);
    }
}
