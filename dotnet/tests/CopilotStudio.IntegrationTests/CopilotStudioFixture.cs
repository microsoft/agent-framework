// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformance.IntegrationTests.Support;
using CopilotStudio.IntegrationTests.Support;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.CopilotStudio;
using Microsoft.Agents.CopilotStudio.Client;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Shared.IntegrationTests;

namespace CopilotStudio.IntegrationTests;

public class CopilotStudioFixture : IAgentFixture
{
    public AIAgent Agent { get; private set; } = null!;

    public Task<List<ChatMessage>> GetChatHistoryAsync(AIAgent agent, AgentSession session) =>
        throw new NotSupportedException("CopilotStudio doesn't allow retrieval of chat history.");

    public Task DeleteSessionAsync(AgentSession session) =>
        // Chat Completion does not require/support deleting threads, so this is a no-op.
        Task.CompletedTask;

    public ValueTask InitializeAsync()
    {
        const string CopilotStudioHttpClientName = nameof(CopilotStudioAgent);

        CopilotStudioConnectionSettings? settings = null;
        try
        {
            settings = new CopilotStudioConnectionSettings(
                TestConfiguration.GetRequiredValue(TestSettings.CopilotStudioTenantId),
                TestConfiguration.GetRequiredValue(TestSettings.CopilotStudioAgentAppId))
            {
                DirectConnectUrl = TestConfiguration.GetRequiredValue(TestSettings.CopilotStudioDirectConnectUrl),
            };
        }
        catch (InvalidOperationException ex)
        {
            Assert.Skip("CopilotStudio configuration could not be loaded. Error:" + ex.Message);
        }

        ServiceCollection services = new();

        services
            .AddSingleton(settings)
            .AddSingleton<CopilotStudioTokenHandler>()
            .AddHttpClient(CopilotStudioHttpClientName)
            .ConfigurePrimaryHttpMessageHandler<CopilotStudioTokenHandler>();

        IHttpClientFactory httpClientFactory =
            services
                .BuildServiceProvider()
                .GetRequiredService<IHttpClientFactory>();

        CopilotClient client = new(settings, httpClientFactory, NullLogger.Instance, CopilotStudioHttpClientName);

        this.Agent = new CopilotStudioAgent(client);

        return default;
    }

    public ValueTask DisposeAsync()
    {
        GC.SuppressFinalize(this);
        return default;
    }
}
