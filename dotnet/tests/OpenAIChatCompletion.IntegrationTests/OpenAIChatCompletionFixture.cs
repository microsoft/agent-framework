// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Agents;
using Microsoft.Extensions.AI;
using OpenAI;
using Shared.IntegrationTests;

namespace OpenAIChatCompletion.IntegrationTests;

public class OpenAIChatCompletionFixture : IChatClientAgentFixture
{
    private static readonly OpenAIConfiguration s_config = TestConfiguration.LoadSection<OpenAIConfiguration>();

#pragma warning disable CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.
    private IChatClient _chatClient;
    private Agent _agent;
#pragma warning restore CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.

    public Agent Agent => this._agent;

    public IChatClient ChatClient => this._chatClient;

    public async Task<List<ChatMessage>> GetChatHistoryAsync(AgentThread thread)
    {
        if (thread is not ChatClientAgentThread chatClientThread)
        {
            throw new InvalidOperationException("The thread must be of type ChatClientAgentThread to retrieve chat history.");
        }

        return await chatClientThread.GetMessagesAsync().ToListAsync();
    }

    public Task<ChatClientAgent> CreateAgentWithInstructionsAsync(string instructions)
    {
        this._chatClient = new OpenAIClient(s_config.ApiKey)
            .GetChatClient(s_config.ChatModelId)
            .AsIChatClient();

        return Task.FromResult(new ChatClientAgent(this._chatClient, new()
        {
            Name = "HelpfulAssistant",
            Instructions = instructions,
        }));
    }

    public Task DeleteAgentAsync(ChatClientAgent agent)
    {
        // Chat Completion does not require/support deleting agents, so this is a no-op.
        return Task.CompletedTask;
    }

    public Task DeleteThreadAsync(AgentThread thread)
    {
        // Chat Completion does not require/support deleting threads, so this is a no-op.
        return Task.CompletedTask;
    }

    public Task InitializeAsync()
    {
        this._chatClient = new OpenAIClient(s_config.ApiKey)
            .GetChatClient(s_config.ChatModelId)
            .AsIChatClient();

        this._agent =
            new ChatClientAgent(this._chatClient, new()
            {
                Name = "HelpfulAssistant",
                Instructions = "You are a helpful assistant.",
            });

        return Task.CompletedTask;
    }

    public Task DisposeAsync()
    {
        this._chatClient.Dispose();
        return Task.CompletedTask;
    }
}
