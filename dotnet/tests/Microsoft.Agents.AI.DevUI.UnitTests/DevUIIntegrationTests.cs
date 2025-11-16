// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net.Http.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.DevUI.Entities;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.DevUI.UnitTests;

public class DevUIIntegrationTests
{
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
}
