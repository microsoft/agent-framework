// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformanceTests;
using Microsoft.Agents;
using Microsoft.Extensions.AI;
using OpenAI;

namespace OpenAIChatCompletion.IntegrationTests;

public class OpenAIChatCompletionFixture : AgentFixture
{
#pragma warning disable CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.
    private IChatClient _chatClient;
    private Agent _agent;
    private AgentThread _agentThread;
#pragma warning restore CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.

    public override Agent Agent => this._agent;

    public override AgentThread AgentThread => this._agentThread;

    public override Task<List<ChatMessage>> GetChatHistory()
    {
        throw new System.NotImplementedException();
    }

    public override Task InitializeAsync()
    {
        var config = TestConfiguration.LoadSection<OpenAIConfiguration>();

        this._chatClient = new OpenAIClient(config.ApiKey)
            .GetChatClient(config.ChatModelId)
            .AsIChatClient();

        this._agentThread = new ChatClientAgentThread();

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
