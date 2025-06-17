// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using AgentConformanceTests;
using Microsoft.Agents;
using Microsoft.Extensions.AI;
using OpenAI;
using Shared.IntegrationTests;

namespace OpenAIChatCompletion.IntegrationTests;

public class OpenAIChatCompletionFixture : AgentFixture
{
#pragma warning disable CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.
    private IChatClient _chatClient;
    private Agent _agent;
#pragma warning restore CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.

    public override Agent Agent => this._agent;

    public override async Task<List<ChatMessage>> GetChatHistoryAsync(AgentThread thread)
    {
        if (thread is not ChatClientAgentThread chatClientThread)
        {
            throw new InvalidOperationException("The thread must be of type ChatClientAgentThread to retrieve chat history.");
        }

        return await chatClientThread.GetMessagesAsync().ToListAsync();
    }

    public override Task DeleteThreadAsync(AgentThread thread)
    {
        // Chat Completion does not require/support deleting threads, so this is a no-op.
        return Task.CompletedTask;
    }

    public override Task InitializeAsync()
    {
        var config = TestConfiguration.LoadSection<OpenAIConfiguration>();

        this._chatClient = new OpenAIClient(config.ApiKey)
            .GetChatClient(config.ChatModelId)
            .AsIChatClient();

        this._agent =
            new ChatClientAgent(this._chatClient, new()
            {
                Name = "HelpfulAssistant",
                Instructions = "You are a helpful assistant.",
            });

        return Task.CompletedTask;
    }

    public override Task DisposeAsync()
    {
        this._chatClient.Dispose();
        return Task.CompletedTask;
    }
}
