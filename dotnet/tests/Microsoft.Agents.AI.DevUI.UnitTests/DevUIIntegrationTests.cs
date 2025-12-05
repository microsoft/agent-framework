// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net.Http.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.DevUI.Entities;
using Microsoft.Agents.AI.Workflows;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.DevUI.UnitTests;

public class DevUIIntegrationTests
{
    private sealed class NoOpExecutor(string id) : Executor(id)
    {
        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
            routeBuilder.AddHandler<object>(
                (msg, ctx) => ctx.SendMessageAsync(msg));
    }

    [Fact]
    public async Task TestServerWithDevUI_ResolvesRequestToWorkflow_ByKeyAsync()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        var mockChatClient = new Mock<IChatClient>();
        var agent = new ChatClientAgent(mockChatClient.Object, "Test", "agent-name");

        builder.Services.AddKeyedSingleton<AIAgent>("registration-key", agent);
        builder.Services.AddDevUI();

        using WebApplication app = builder.Build();
        app.MapDevUI();

        await app.StartAsync();

        // Act
        var resolvedAgent = app.Services.GetKeyedService<AIAgent>("registration-key");
        var client = app.GetTestClient();
        var response = await client.GetAsync(new Uri("/v1/entities", uriKind: UriKind.Relative));

        var discoveryResponse = await response.Content.ReadFromJsonAsync<DiscoveryResponse>();
        Assert.NotNull(discoveryResponse);
        Assert.Single(discoveryResponse.Entities);
        Assert.Equal("agent-name", discoveryResponse.Entities[0].Name);
    }

    [Fact]
    public async Task TestServerWithDevUI_ResolvesMultipleAIAgents_ByKeyAsync()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        var mockChatClient = new Mock<IChatClient>();
        var agent1 = new ChatClientAgent(mockChatClient.Object, "Test", "agent-one");
        var agent2 = new ChatClientAgent(mockChatClient.Object, "Test", "agent-two");
        var agent3 = new ChatClientAgent(mockChatClient.Object, "Test", "agent-three");

        builder.Services.AddKeyedSingleton<AIAgent>("key-1", agent1);
        builder.Services.AddKeyedSingleton<AIAgent>("key-2", agent2);
        builder.Services.AddKeyedSingleton<AIAgent>("key-3", agent3);
        builder.Services.AddDevUI();

        using WebApplication app = builder.Build();
        app.MapDevUI();

        await app.StartAsync();

        // Act
        var client = app.GetTestClient();
        var response = await client.GetAsync(new Uri("/v1/entities", uriKind: UriKind.Relative));

        var discoveryResponse = await response.Content.ReadFromJsonAsync<DiscoveryResponse>();

        // Assert
        Assert.NotNull(discoveryResponse);
        Assert.Equal(3, discoveryResponse.Entities.Count);
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "agent-one" && e.Type == "agent");
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "agent-two" && e.Type == "agent");
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "agent-three" && e.Type == "agent");
    }

    [Fact]
    public async Task TestServerWithDevUI_ResolvesAIAgents_WithKeyedAndDefaultRegistrationAsync()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        var mockChatClient = new Mock<IChatClient>();
        var agentKeyed1 = new ChatClientAgent(mockChatClient.Object, "Test", "keyed-agent-one");
        var agentKeyed2 = new ChatClientAgent(mockChatClient.Object, "Test", "keyed-agent-two");
        var agentDefault = new ChatClientAgent(mockChatClient.Object, "Test", "default-agent");

        builder.Services.AddKeyedSingleton<AIAgent>("key-1", agentKeyed1);
        builder.Services.AddKeyedSingleton<AIAgent>("key-2", agentKeyed2);
        builder.Services.AddSingleton<AIAgent>(agentDefault);
        builder.Services.AddDevUI();

        using WebApplication app = builder.Build();
        app.MapDevUI();

        await app.StartAsync();

        // Act
        var client = app.GetTestClient();
        var response = await client.GetAsync(new Uri("/v1/entities", uriKind: UriKind.Relative));

        var discoveryResponse = await response.Content.ReadFromJsonAsync<DiscoveryResponse>();

        // Assert
        Assert.NotNull(discoveryResponse);
        Assert.Equal(3, discoveryResponse.Entities.Count);
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "keyed-agent-one" && e.Type == "agent");
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "keyed-agent-two" && e.Type == "agent");
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "default-agent" && e.Type == "agent");
    }

    [Fact]
    public async Task TestServerWithDevUI_ResolvesMultipleWorkflows_ByKeyAsync()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        var workflow1 = new WorkflowBuilder("executor-1")
            .WithName("workflow-one")
            .WithDescription("First workflow")
            .BindExecutor(new NoOpExecutor("executor-1"))
            .Build();

        var workflow2 = new WorkflowBuilder("executor-2")
            .WithName("workflow-two")
            .WithDescription("Second workflow")
            .BindExecutor(new NoOpExecutor("executor-2"))
            .Build();

        var workflow3 = new WorkflowBuilder("executor-3")
            .WithName("workflow-three")
            .WithDescription("Third workflow")
            .BindExecutor(new NoOpExecutor("executor-3"))
            .Build();

        builder.Services.AddKeyedSingleton("key-1", workflow1);
        builder.Services.AddKeyedSingleton("key-2", workflow2);
        builder.Services.AddKeyedSingleton("key-3", workflow3);
        builder.Services.AddDevUI();

        using WebApplication app = builder.Build();
        app.MapDevUI();

        await app.StartAsync();

        // Act
        var client = app.GetTestClient();
        var response = await client.GetAsync(new Uri("/v1/entities", uriKind: UriKind.Relative));

        var discoveryResponse = await response.Content.ReadFromJsonAsync<DiscoveryResponse>();

        // Assert
        Assert.NotNull(discoveryResponse);
        Assert.Equal(3, discoveryResponse.Entities.Count);
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "workflow-one" && e.Type == "workflow");
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "workflow-two" && e.Type == "workflow");
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "workflow-three" && e.Type == "workflow");
    }

    [Fact]
    public async Task TestServerWithDevUI_ResolvesWorkflows_WithKeyedAndDefaultRegistrationAsync()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        var workflowKeyed1 = new WorkflowBuilder("executor-1")
            .WithName("keyed-workflow-one")
            .BindExecutor(new NoOpExecutor("executor-1"))
            .Build();

        var workflowKeyed2 = new WorkflowBuilder("executor-2")
            .WithName("keyed-workflow-two")
            .BindExecutor(new NoOpExecutor("executor-2"))
            .Build();

        var workflowDefault = new WorkflowBuilder("executor-default")
            .WithName("default-workflow")
            .BindExecutor(new NoOpExecutor("executor-default"))
            .Build();

        builder.Services.AddKeyedSingleton("key-1", workflowKeyed1);
        builder.Services.AddKeyedSingleton("key-2", workflowKeyed2);
        builder.Services.AddSingleton(workflowDefault);
        builder.Services.AddDevUI();

        using WebApplication app = builder.Build();
        app.MapDevUI();

        await app.StartAsync();

        // Act
        var client = app.GetTestClient();
        var response = await client.GetAsync(new Uri("/v1/entities", uriKind: UriKind.Relative));

        var discoveryResponse = await response.Content.ReadFromJsonAsync<DiscoveryResponse>();

        // Assert
        Assert.NotNull(discoveryResponse);
        Assert.Equal(3, discoveryResponse.Entities.Count);
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "keyed-workflow-one" && e.Type == "workflow");
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "keyed-workflow-two" && e.Type == "workflow");
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "default-workflow" && e.Type == "workflow");
    }

    [Fact]
    public async Task TestServerWithDevUI_ResolvesMixedAgentsAndWorkflows_AllRegistrationsAsync()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        var mockChatClient = new Mock<IChatClient>();

        // Create AIAgents
        var agent1 = new ChatClientAgent(mockChatClient.Object, "Test", "mixed-agent-one");
        var agent2 = new ChatClientAgent(mockChatClient.Object, "Test", "mixed-agent-two");
        var agentDefault = new ChatClientAgent(mockChatClient.Object, "Test", "default-mixed-agent");

        // Create Workflows
        var workflow1 = new WorkflowBuilder("executor-1")
            .WithName("mixed-workflow-one")
            .BindExecutor(new NoOpExecutor("executor-1"))
            .Build();

        var workflow2 = new WorkflowBuilder("executor-2")
            .WithName("mixed-workflow-two")
            .BindExecutor(new NoOpExecutor("executor-2"))
            .Build();

        var workflowDefault = new WorkflowBuilder("executor-default")
            .WithName("default-mixed-workflow")
            .BindExecutor(new NoOpExecutor("executor-default"))
            .Build();

        // Register all
        builder.Services.AddKeyedSingleton<AIAgent>("agent-key-1", agent1);
        builder.Services.AddKeyedSingleton<AIAgent>("agent-key-2", agent2);
        builder.Services.AddSingleton<AIAgent>(agentDefault);
        builder.Services.AddKeyedSingleton("workflow-key-1", workflow1);
        builder.Services.AddKeyedSingleton("workflow-key-2", workflow2);
        builder.Services.AddSingleton(workflowDefault);
        builder.Services.AddDevUI();

        using WebApplication app = builder.Build();
        app.MapDevUI();

        await app.StartAsync();

        // Act
        var client = app.GetTestClient();
        var response = await client.GetAsync(new Uri("/v1/entities", uriKind: UriKind.Relative));

        var discoveryResponse = await response.Content.ReadFromJsonAsync<DiscoveryResponse>();

        // Assert
        Assert.NotNull(discoveryResponse);
        Assert.Equal(6, discoveryResponse.Entities.Count);

        // Verify agents
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "mixed-agent-one" && e.Type == "agent");
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "mixed-agent-two" && e.Type == "agent");
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "default-mixed-agent" && e.Type == "agent");

        // Verify workflows
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "mixed-workflow-one" && e.Type == "workflow");
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "mixed-workflow-two" && e.Type == "workflow");
        Assert.Contains(discoveryResponse.Entities, e => e.Name == "default-mixed-workflow" && e.Type == "workflow");
    }
}
