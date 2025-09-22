// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformance.IntegrationTests.Support;
using CopilotStudio.IntegrationTests.Support;
using Microsoft.Agents.CopilotStudio.Client;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.CopilotStudio;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;

namespace CopilotStudio.IntegrationTests;

public class CopilotStudioFixture : IAgentFixture
{
    public AIAgent Agent { get; private set; } = null!;

    public Task<List<ChatMessage>> GetChatHistoryAsync(AgentThread thread) =>
        throw new NotSupportedException("CopilotStudio doesn't allow retrieval of chat history.");

    public Task DeleteThreadAsync(AgentThread thread) =>
        // Chat Completion does not require/support deleting threads, so this is a no-op.
        Task.CompletedTask;

    public Task InitializeAsync()
    {
        const string CopilotStudioHttpClientName = nameof(CopilotStudioAgent);

        var config = TestConfiguration.LoadSection<CopilotStudioAgentConfiguration>();
        var settings = new CopilotStudioConnectionSettings(config.TenantId, config.AppClientId)
        {
            DirectConnectUrl = config.DirectConnectUrl,
        };

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

        return Task.CompletedTask;
    }

    public Task DisposeAsync() => Task.CompletedTask;
}
