// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents;
using Microsoft.Agents.CopilotStudio;
using Microsoft.Agents.CopilotStudio.Client;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Samples;

namespace GettingStarted.Providers;

public class CopilotStudioAgentRun(ITestOutputHelper output) : AgentSample(output)
{
    [Fact]
    public async Task RunWithCopilotStudioAgent()
    {
        const string CopilotStudioHttpClientName = nameof(CopilotStudioAgentRun);

        var config = TestConfiguration.CopilotStudio;
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

        Agent agent = new CopilotStudioAgent(client, "FriendlyAssistant", "Friendly Assistant");

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input
        await RunAgentAsync("Tell me a joke about a pirate.");
        await RunAgentAsync("Now add some emojis to the joke.");

        // Local function to run agent and display the conversation messages for the thread.
        async Task RunAgentAsync(string input)
        {
            this.WriteUserMessage(input);

            var response = await agent.RunAsync(input, thread);

            this.WriteResponseOutput(response);
        }
    }
}
