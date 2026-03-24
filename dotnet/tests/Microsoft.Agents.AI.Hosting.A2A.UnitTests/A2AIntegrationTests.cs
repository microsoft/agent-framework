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
    /// Verifies that calling the A2A well-known agent card endpoint returns the configured agent card.
    /// </summary>
    /// <remarks>
    /// Skipped on .NET 8 because the A2A.AspNetCore SDK's MapWellKnownAgentCard uses
    /// PipeWriter.UnflushedBytes which requires .NET 9+.
    /// </remarks>
#if NET9_0_OR_GREATER
    [Fact]
#else
    [Fact(Skip = "A2A.AspNetCore MapWellKnownAgentCard requires .NET 9+ (PipeWriter.UnflushedBytes)")]
#endif
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
            Version = "1.0",
            SupportedInterfaces =
            [
                new AgentInterface { Url = "http://localhost/a2a/test-agent" }
            ]
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

            // Act - Query the well-known agent card endpoint
            var requestUri = new Uri("/.well-known/agent-card.json", UriKind.Relative);
            var response = await httpClient.GetAsync(requestUri);

            // Assert
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

            // Verify the card has a supportedInterfaces property with a URL
            Assert.True(root.TryGetProperty("supportedInterfaces", out var interfacesProp));
            Assert.NotEqual(JsonValueKind.Null, interfacesProp.ValueKind);
            Assert.True(interfacesProp.GetArrayLength() > 0);

            var firstInterface = interfacesProp[0];
            Assert.True(firstInterface.TryGetProperty("url", out var urlProperty));
            var url = urlProperty.GetString();
            Assert.NotNull(url);
            Assert.NotEmpty(url);
            Assert.Equal("http://localhost/a2a/test-agent", url);
        }
        finally
        {
            await app.StopAsync();
        }
    }
}
