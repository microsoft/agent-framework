// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.Channels.UnitTests;

public class HostCompositionTests
{
    [Fact]
    public void AddAgentFrameworkHost_WithChannel_ComposesHost()
    {
        // Arrange
        var builder = Host.CreateApplicationBuilder();
        var echo = new EchoExecutor();
        var workflow = new WorkflowBuilder(echo).WithOutputFrom(echo).Build();

        // Act
        builder.AddAgentFrameworkHost(workflow).AddChannel(new FakeChannel());
        using var app = builder.Build();
        var host = app.Services.GetRequiredService<AgentFrameworkHost>();

        // Assert
        Assert.Single(host.Channels);
        Assert.Equal("fake", host.Channels[0].Name);
        Assert.IsType<WorkflowRunner>(host.TargetRunner);
    }

    [Fact]
    public async Task Host_RunAsync_DrivesWorkflowTargetAsync()
    {
        // Arrange
        var builder = Host.CreateApplicationBuilder();
        var echo = new EchoExecutor();
        var workflow = new WorkflowBuilder(echo).WithOutputFrom(echo).Build();
        builder.AddAgentFrameworkHost(workflow).AddChannel(new FakeChannel());
        using var app = builder.Build();
        var host = app.Services.GetRequiredService<AgentFrameworkHost>();

        // Act
        var result = await host.RunAsync(new ChannelRequest("fake", "message.create", "hi"), CancellationToken.None);

        // Assert
        var typed = Assert.IsType<HostedRunResult<WorkflowRunResult>>(result);
        Assert.Equal(WorkflowRunStatus.Completed, typed.Result.Status);
    }

    private sealed class FakeChannel : Channel
    {
        public override string Name => "fake";
        public override ChannelContribution Contribute(ChannelContext context) => new();
    }

    private sealed class EchoExecutor() : Executor<string, string>("EchoExecutor")
    {
        public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default) =>
            ValueTask.FromResult($"echo: {message}");
    }
}
