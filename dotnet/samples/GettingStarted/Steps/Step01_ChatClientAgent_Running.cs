// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Steps;

/// <summary>
/// Provides test methods to demonstrate the usage of chat agents with different interaction models.
/// </summary>
/// <remarks>This class contains examples of using <see cref="ChatClientAgent"/> to showcase scenarios with and without conversation history.
/// Each test method demonstrates how to configure and interact with the agents, including handling user input and displaying responses.
/// </remarks>
public sealed class Step01_ChatClientAgent_Running(ITestOutputHelper output) : AgentSample(output)
{
    private const string ParrotName = "Parrot";
    private const string ParrotInstructions = "Repeat the user message in the voice of a pirate and then end with a parrot sound.";

    /// <summary>
    /// Demonstrate the most basic Agent case, where we do not have a server-side agent
    /// but just an in-memory agent, backed by an inference service,
    /// and we are invoking with text input, and getting back a text response.
    /// </summary>
    [Theory]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    [InlineData(ChatClientProviders.OpenAIChatCompletion)]
    [InlineData(ChatClientProviders.OpenAIResponses)]
    public async Task RunBasic(ChatClientProviders provider)
    {
        // Get the chat client to communicate with the inference service backing our agent.
        // Any implementation of Microsoft.Extensions.AI.Agents.IChatClient can be used with the ChatClientAgent.
        // See the Providers folder for examples on how to create chat clients for some sample providers.
        IChatClient chatClient = base.GetChatClient(provider);

        // Define the agent
        AIAgent agent = new ChatClientAgent(chatClient, ParrotInstructions, ParrotName);

        // Invoke the agent and output the text result.
        Console.WriteLine(await agent.RunAsync("Fortune favors the bold."));
    }

    /// <summary>
    /// Demonstrate the usage of <see cref="ChatClientAgent"/> where each invocation is
    /// a unique interaction with no conversation history between them.
    /// </summary>
    [Theory]
    [InlineData(ChatClientProviders.AzureAIAgentsPersistent)]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    [InlineData(ChatClientProviders.OpenAIAssistant)]
    [InlineData(ChatClientProviders.OpenAIChatCompletion)]
    [InlineData(ChatClientProviders.OpenAIResponses)]
    public async Task RunWithoutThread(ChatClientProviders provider)
    {
        // Define the options for the chat client agent.
        var agentOptions = new ChatClientAgentOptions
        {
            Name = ParrotName,
            Instructions = ParrotInstructions,
        };

        // Create the server-side agent Id when applicable (depending on the provider).
        agentOptions.Id = await base.AgentCreateAsync(provider, agentOptions);

        // Get the chat client to use for the agent.
        using var chatClient = base.GetChatClient(provider, agentOptions);

        // Define the agent
        var agent = new ChatClientAgent(chatClient, agentOptions);

        // Respond to user input
        await RunAgentAsync("Fortune favors the bold.");
        await RunAgentAsync("I came, I saw, I conquered.");
        await RunAgentAsync("Practice makes perfect.");

        // Local function to invoke agent and display the conversation messages.
        async Task RunAgentAsync(string input)
        {
            this.WriteUserMessage(input);

            var response = await agent.RunAsync(input);
            this.WriteResponseOutput(response);
        }

        // Clean up the server-side agent after use when applicable (depending on the provider).
        await base.AgentCleanUpAsync(provider, agent);
    }

    /// <summary>
    /// Demonstrate the usage of <see cref="ChatClientAgent"/> where a conversation history is maintained.
    /// </summary>
    [Theory]
    [InlineData(ChatClientProviders.AzureAIAgentsPersistent)]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    [InlineData(ChatClientProviders.OpenAIAssistant)]
    [InlineData(ChatClientProviders.OpenAIResponses_InMemoryMessageThread)]
    [InlineData(ChatClientProviders.OpenAIResponses_ConversationIdThread)]
    public async Task RunWithThread(ChatClientProviders provider)
    {
        // Define the options for the chat client agent.
        var agentOptions = new ChatClientAgentOptions
        {
            Name = ParrotName,
            Instructions = ParrotInstructions,

            // Get chat options based on the store type, if needed.
            ChatOptions = base.GetChatOptions(provider),
        };

        // Create the server-side agent Id when applicable (depending on the provider).
        agentOptions.Id = await base.AgentCreateAsync(provider, agentOptions);

        // Get the chat client to use for the agent.
        using var chatClient = base.GetChatClient(provider, agentOptions);

        // Define the agent
        var agent = new ChatClientAgent(chatClient, agentOptions);

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input
        await RunAgentAsync("Tell me a joke about a pirate.");
        await RunAgentAsync("Now add some emojis to the joke.");

        // Local function to invoke agent and display the conversation messages for the thread.
        async Task RunAgentAsync(string input)
        {
            this.WriteUserMessage(input);

            var response = await agent.RunAsync(input, thread);

            this.WriteResponseOutput(response);
        }

        // Clean up the server-side agent and thread after use when applicable (depending on the provider).
        await base.AgentCleanUpAsync(provider, agent, thread);
    }

    /// <summary>
    /// Demonstrate the usage of <see cref="ChatClientAgent"/> in streaming mode,
    /// where a conversation is maintained by the <see cref="AgentThread"/>.
    /// </summary>
    [Theory]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    [InlineData(ChatClientProviders.AzureAIAgentsPersistent)]
    [InlineData(ChatClientProviders.OpenAIAssistant)]
    [InlineData(ChatClientProviders.OpenAIResponses_InMemoryMessageThread)]
    [InlineData(ChatClientProviders.OpenAIResponses_ConversationIdThread)]
    public async Task RunStreamingWithThread(ChatClientProviders provider)
    {
        // Define the options for the chat client agent.
        var agentOptions = new ChatClientAgentOptions
        {
            Name = ParrotName,
            Instructions = ParrotInstructions,

            // Get chat options based on the store type, if needed.
            ChatOptions = base.GetChatOptions(provider),
        };

        // Create the server-side agent Id when applicable (depending on the provider).
        agentOptions.Id = await base.AgentCreateAsync(provider, agentOptions);

        // Get the chat client to use for the agent.
        using var chatClient = base.GetChatClient(provider, agentOptions);

        // Define the agent
        var agent = new ChatClientAgent(chatClient, agentOptions);

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input
        await RunAgentAsync("Tell me a joke about a pirate.");
        await RunAgentAsync("Now add some emojis to the joke.");

        // Local function to invoke agent and display the conversation messages.
        async Task RunAgentAsync(string input)
        {
            this.WriteUserMessage(input);

            await foreach (var update in agent.RunStreamingAsync(input, thread))
            {
                this.WriteAgentOutput(update);
            }
        }

        // Clean up the server-side agent and thread after use when applicable (depending on the provider).
        await base.AgentCleanUpAsync(provider, agent, thread);
    }
}
