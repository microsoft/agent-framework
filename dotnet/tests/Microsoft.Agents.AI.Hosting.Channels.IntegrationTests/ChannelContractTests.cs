// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using System.Net.Http;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;
using Microsoft.Agents.AI.Hosting.Channels.Responses;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests;

/// <summary>
/// Exercises the channel/host contract directly: route aggregation under <see cref="Channel.Path"/>,
/// lifecycle callbacks, endpoint filters, the run/stream invocation seam, hook ordering, multi-channel
/// composition, and target neutrality.
/// </summary>
public class ChannelContractTests
{
    [Fact]
    public async Task Routes_MountUnderChannelPathAsync()
    {
        // Arrange
        var probe = new ProbeChannel(path: "/probe");
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddChannel(probe));

        // Act
        var ok = await app.Client.GetAsync(new System.Uri("http://localhost/probe/ping"));
        var miss = await app.Client.GetAsync(new System.Uri("http://localhost/ping"));

        // Assert
        Assert.Equal(HttpStatusCode.OK, ok.StatusCode);
        Assert.Equal("pong", await ok.Content.ReadAsStringAsync());
        Assert.Equal(HttpStatusCode.NotFound, miss.StatusCode);
    }

    [Fact]
    public async Task CustomPath_IsHonoredAsync()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddChannel(new ProbeChannel(path: "/probe2")));

        // Act
        var moved = await app.Client.GetAsync(new System.Uri("http://localhost/probe2/ping"));
        var old = await app.Client.GetAsync(new System.Uri("http://localhost/probe/ping"));

        // Assert
        Assert.Equal(HttpStatusCode.OK, moved.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, old.StatusCode);
    }

    [Fact]
    public async Task Lifecycle_StartupAndShutdownCallbacksFireAsync()
    {
        // Arrange
        var probe = new ProbeChannel();
        var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddChannel(probe));

        // Assert - startup fired during StartAsync
        Assert.True(probe.StartupFired);
        Assert.False(probe.ShutdownFired);

        // Act - dispose stops the host
        await app.DisposeAsync();

        // Assert - shutdown fired during StopAsync
        Assert.True(probe.ShutdownFired);
    }

    [Fact]
    public async Task EndpointFilter_AppliedToChannelGroupAsync()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddChannel(new ProbeChannel()));

        // Act
        var response = await app.Client.GetAsync(new System.Uri("http://localhost/probe/ping"));

        // Assert
        Assert.True(response.Headers.TryGetValues("x-probe-filter", out var values));
        Assert.Contains("applied", values!);
    }

    [Fact]
    public async Task RunSeam_InvokesTargetAsync()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddChannel(new ProbeChannel()));

        // Act
        var response = await app.Client.PostAsync(new System.Uri("http://localhost/probe/run"), new StringContent("hi"));

        // Assert
        Assert.Equal(FakeChatAgent.Reply, await response.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task StreamSeam_YieldsUpdatesThenOneCompletedAsync()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddChannel(new ProbeChannel()));

        // Act
        var response = await app.Client.PostAsync(new System.Uri("http://localhost/probe/stream"), new StringContent("hi"));
        var body = await response.Content.ReadAsStringAsync();

        // Assert - 8 update chunks, exactly one completed terminal
        Assert.Equal("updates=8;completed=1", body);
    }

    [Fact]
    public async Task MultipleChannels_ShareOneHostAndTargetAsync()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b
            .AddAgentFrameworkHost(new FakeChatAgent())
            .AddChannel(new ProbeChannel())
            .AddResponsesChannel());

        // Act
        var probe = await app.Client.PostAsync(new System.Uri("http://localhost/probe/run"), new StringContent("hi"));
        var responses = await app.Client.PostAsync(new System.Uri("http://localhost/responses"), JsonBody("{ \"input\": \"hi\" }"));

        // Assert - both channels reachable, both hit the same fake target
        Assert.Equal(HttpStatusCode.OK, probe.StatusCode);
        Assert.Equal(FakeChatAgent.Reply, await probe.Content.ReadAsStringAsync());
        Assert.Equal(HttpStatusCode.OK, responses.StatusCode);
        Assert.Contains(FakeChatAgent.Reply, await responses.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task TargetNeutrality_SameChannelWorksForAgentAndWorkflowAsync()
    {
        // Arrange + Act - agent target
        await using (var agentApp = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddChannel(new ProbeChannel())))
        {
            var agentResponse = await agentApp.Client.PostAsync(new System.Uri("http://localhost/probe/run"), new StringContent("hi"));
            Assert.Equal(HttpStatusCode.OK, agentResponse.StatusCode);
        }

        // Arrange + Act - workflow target, identical channel
        var workflow = WorkflowFactory.Echo();
        await using var workflowApp = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(workflow).AddChannel(new ProbeChannel()));
        var workflowResponse = await workflowApp.Client.PostAsync(new System.Uri("http://localhost/probe/run"), new StringContent("hi"));

        // Assert - the same probe channel drove a workflow target without branching on type
        Assert.Equal(HttpStatusCode.OK, workflowResponse.StatusCode);
    }

    private static StringContent JsonBody(string json) => new(json, System.Text.Encoding.UTF8, "application/json");
}
