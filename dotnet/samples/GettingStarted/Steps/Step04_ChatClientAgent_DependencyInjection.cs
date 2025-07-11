// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.DependencyInjection;

namespace Steps;

public sealed class Step04_ChatClientAgent_DependencyInjection(ITestOutputHelper output) : AgentSample(output)
{
    [Theory]
    [InlineData(ChatClientProviders.AzureAIAgentsPersistent)]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    [InlineData(ChatClientProviders.OpenAIAssistant)]
    [InlineData(ChatClientProviders.OpenAIChatCompletion)]
    [InlineData(ChatClientProviders.OpenAIResponses)]
    public async Task RunningWithServiceCollection(ChatClientProviders provider)
    {
        // Adding multiple chat clients to the service collection.
        var services = new ServiceCollection();

        var agentOptions = new ChatClientAgentOptions
        {
            Name = "Parrot",
            Instructions = "Repeat the user message in the voice of a pirate and then end with a parrot sound.",

            // Get chat options based on the store type, if needed.
            ChatOptions = base.GetChatOptions(provider),
        };

        // Create the server-side agent Id when applicable (depending on the provider).
        agentOptions.Id = await base.AgentCreateAsync(provider, agentOptions);

        services.AddSingleton(agentOptions);

        services.AddChatClient((sp) => base.GetChatClient(provider, sp.GetRequiredService<ChatClientAgentOptions>()));

        services.AddSingleton<ChatClientAgent>();

        // Build the service provider.
        using var serviceProvider = services.BuildServiceProvider();

        // Get the agent from the service provider.
        var agent = serviceProvider.GetRequiredService<ChatClientAgent>();

        // Create the chat history thread to capture the agent interaction.
        var thread = agent.GetNewThread();

        Console.WriteLine($"Using chat client for provider: {agent.ChatClient.GetService<ChatClientMetadata>()!.ProviderName}, for agent: {agent.Name}");

        // Respond to user input, invoking functions where appropriate.
        await RunAgentAsync("Tell me a joke about a pirate.");
        await RunAgentAsync("Now add some emojis to the joke.");

        async Task RunAgentAsync(string input)
        {
            this.WriteUserMessage(input);
            var response = await agent.RunAsync(input, thread);
            this.WriteResponseOutput(response);
        }

        // Clean up the agent and thread after use when applicable (depending on the provider).
        await base.AgentCleanUpAsync(provider, agent, thread);
    }
}
