// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading.Tasks;
using A2A;
using Microsoft.Agents.AI.Hosting.A2A.UnitTests.Internal;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.A2A.UnitTests;

public sealed class A2AIntegrationTests
{
    /// <summary>
    /// Verifies that calling the A2A card endpoint with MapA2A returns an agent card with a URL populated.
    /// </summary>
    [Fact]
    public async Task MapA2A_WithAgentCard_CardEndpointReturnsCardWithUrlAsync()
    {
        // Arrange
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        IChatClient mockChatClient = new DummyChatClient();
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        IHostedAgentBuilder agentBuilder = builder.AddAIAgent("test-agent", "Test instructions", chatClientServiceKey: "chat-client");
        builder.Services.AddLogging();

        using WebApplication app = builder.Build();

        var agentCard = new AgentCard
        {
            Name = "Test Agent",
            Description = "A test agent for A2A communication",
            Version = "1.0"
        };

        // Map A2A with the agent card
        app.MapA2A(agentBuilder, "/a2a/test-agent", agentCard);

        await app.StartAsync();

        try
        {
            // Get the test server client
            TestServer testServer = app.Services.GetRequiredService<IServer>() as TestServer
                ?? throw new InvalidOperationException("TestServer not found");
            var httpClient = testServer.CreateClient();

            // Act - Query the agent card endpoint
            var requestUri = new Uri("/a2a/test-agent/v1/card", UriKind.Relative);
            var response = await httpClient.GetAsync(requestUri);

            // Assert
            Assert.True(response.IsSuccessStatusCode, $"Expected successful response but got {response.StatusCode}");

            var content = await response.Content.ReadAsStringAsync();
            var jsonDoc = JsonDocument.Parse(content);
            var root = jsonDoc.RootElement;

            // Verify the card has expected properties
            Assert.True(root.TryGetProperty("name", out var nameProperty));
            Assert.Equal("Test Agent", nameProperty.GetString());

            Assert.True(root.TryGetProperty("description", out var descProperty));
            Assert.Equal("A test agent for A2A communication", descProperty.GetString());

            // Verify the card has a URL property and it's not null/empty
            Assert.True(root.TryGetProperty("url", out var urlProperty));
            Assert.NotEqual(JsonValueKind.Null, urlProperty.ValueKind);

            var url = urlProperty.GetString();
            Assert.NotNull(url);
            Assert.NotEmpty(url);
            Assert.StartsWith("http", url, StringComparison.OrdinalIgnoreCase);
            Assert.Equal($"{testServer.BaseAddress.ToString().TrimEnd('/')}/a2a/test-agent/v1/card", url);
        }
        finally
        {
            await app.StopAsync();
        }
    }
}
