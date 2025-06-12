// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Samples;
using OpenAI;
using OpenAI.Assistants;

#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

namespace GettingStarted.OpenAIAssistantChatClientAgent;

/// <summary>
/// Provides test methods to demonstrate the usage of chat agents with different interaction models.
/// </summary>
/// <remarks>
/// Each test method demonstrates how to configure and interact with the agents, including handling user input and displaying responses.
/// </remarks>
public sealed class Step01_Running : AgentSample, IAsyncLifetime
{
    private const string ParrotName = "Parrot";
    private const string ParrotInstructions = "Repeat the user message in the voice of a pirate and then end with a parrot sound.";

    private const string JokerName = "Joker";
    private const string JokerInstructions = "You are good at telling jokes.";

    private readonly AssistantClient _assistantClient;
    private string? _assistantId;

    public Step01_Running(ITestOutputHelper output)
        : base(output)
    {
        // Get a client to create server side agents with.
        var openAIClient = new OpenAIClient(TestConfiguration.OpenAI.ApiKey);
        this._assistantClient = openAIClient.GetAssistantClient();
    }

    public async Task InitializeAsync()
    {
        // Create a server side agent to work with.
        var assistantCreateResult = await this._assistantClient.CreateAssistantAsync(
            TestConfiguration.OpenAI.ChatModelId,
            new()
            {
                Name = JokerName,
                Instructions = JokerInstructions
            });

        this._assistantId = assistantCreateResult.Value.Id;
    }

    /// <summary>
    /// Demonstrate the usage of <see cref="ChatClientAgent"/> where a conversation history is maintained.
    /// </summary>
    [Fact]
    public async Task RunWithConversationThread()
    {
        // Get the chat client to use for the agent.
        using var chatClient = this._assistantClient.AsIChatClient(this._assistantId!);

        // Define the agent
        ChatClientAgent agent =
            new(chatClient, new()
            {
                Name = JokerName,
                Instructions = JokerInstructions,
            });

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input
        await InvokeAgentAsync("Tell me a joke about a pirate.");
        await InvokeAgentAsync("Now add some emojis to the joke.");

        // Local function to invoke agent and display the conversation messages for the thread.
        async Task InvokeAgentAsync(string input)
        {
            this.WriteUserMessage(input);

            var response = await agent.RunAsync(input, thread);

            this.WriteResponseOutput(response);
        }

        // Cleanup
        await this._assistantClient.DeleteThreadAsync(thread.Id);
    }

    /// <summary>
    /// Demonstrate the usage of <see cref="ChatClientAgent"/> in streaming mode,
    /// where a conversation is maintained by the <see cref="AgentThread"/>.
    /// </summary>
    [Fact]
    public async Task StreamingRunWithConversationThread()
    {
        // Get the chat client to use for the agent.
        using var chatClient = this._assistantClient.AsIChatClient(this._assistantId!);

        // Define the agent
        ChatClientAgent agent =
            new(chatClient, new()
            {
                Name = ParrotName,
                Instructions = ParrotInstructions,
            });

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input
        await InvokeAgentAsync("Tell me a joke about a pirate.");
        await InvokeAgentAsync("Now add some emojis to the joke.");

        // Local function to invoke agent and display the conversation messages.
        async Task InvokeAgentAsync(string input)
        {
            this.WriteUserMessage(input);

            await foreach (var update in agent.RunStreamingAsync(input, thread))
            {
                this.WriteAgentOutput(update);
            }
        }

        // Cleanup
        await this._assistantClient.DeleteThreadAsync(thread.Id);
    }

    async Task IAsyncLifetime.DisposeAsync()
    {
        await this._assistantClient.DeleteAssistantAsync(this._assistantId);
    }
}
