// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

[Collection(FoundryStateStoreLocalFallbackCollectionDefinition.CollectionName)]
public sealed class HostedResponsesRegistrationTests
{
    [Fact]
    public async Task AddFoundryResponses_HostedBuilder_StartsAsync()
    {
        // Arrange
        string? previousHostingEnvironment =
            Environment.GetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT");
        string? previousProjectEndpoint =
            Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");

        try
        {
            Environment.SetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT", "foundry");
            Environment.SetEnvironmentVariable(
                "FOUNDRY_PROJECT_ENDPOINT",
                "https://example.test/api/projects/test");

            WebApplicationBuilder builder = WebApplication.CreateBuilder();
            builder.WebHost.UseTestServer();
            var agent = new Mock<AIAgent>();
            agent.SetupGet(a => a.Name).Returns("test-agent");

            // Act
            builder.AddFoundryResponses(agent.Object);
            await using WebApplication app = builder.Build();
            app.MapFoundryResponses();
            await app.StartAsync();
            using HttpClient client =
                (app.Services.GetRequiredService<IServer>() as TestServer
                    ?? throw new InvalidOperationException("TestServer not found."))
                .CreateClient();
            using HttpResponseMessage response =
                await client.GetAsync(new Uri("/readiness", UriKind.Relative));

            // Assert
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        }
        finally
        {
            Environment.SetEnvironmentVariable(
                "FOUNDRY_HOSTING_ENVIRONMENT",
                previousHostingEnvironment);
            Environment.SetEnvironmentVariable(
                "FOUNDRY_PROJECT_ENDPOINT",
                previousProjectEndpoint);
        }
    }

    [Fact]
    public async Task AddFoundryResponses_SteeringOnly_StartsAsync()
    {
        // Arrange
        string stateRoot = Path.Combine(
            Path.GetTempPath(),
            $"foundry-steering-startup-{Guid.NewGuid():N}");
        string? previousStateRoot =
            Environment.GetEnvironmentVariable("AGENTSERVER_STATE_ROOT");
        string? previousHostingEnvironment =
            Environment.GetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT");

        try
        {
            Environment.SetEnvironmentVariable("AGENTSERVER_STATE_ROOT", stateRoot);
            Environment.SetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT", null);

            WebApplicationBuilder builder = WebApplication.CreateBuilder();
            builder.WebHost.UseTestServer();
            var agent = new Mock<AIAgent>();
            agent.SetupGet(a => a.Name).Returns("test-agent");

            // Act
            builder.Services.AddFoundryResponses(
                agent.Object,
                new InMemoryAgentSessionStore(),
                options => options.SteerableConversations = true);
            await using WebApplication app = builder.Build();
            app.MapFoundryResponses();
            await app.StartAsync();

            // Assert
            Assert.NotNull(app.Services.GetService<ResponseHandler>());
        }
        finally
        {
            Environment.SetEnvironmentVariable(
                "AGENTSERVER_STATE_ROOT",
                previousStateRoot);
            Environment.SetEnvironmentVariable(
                "FOUNDRY_HOSTING_ENVIRONMENT",
                previousHostingEnvironment);

            if (Directory.Exists(stateRoot))
            {
                Directory.Delete(stateRoot, recursive: true);
            }
        }
    }
}
