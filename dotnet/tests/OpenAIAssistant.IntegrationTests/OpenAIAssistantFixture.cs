// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using AgentConformanceTests;
using Microsoft.Agents;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Assistants;
using Shared.IntegrationTests;

namespace OpenAIAssistant.IntegrationTests;

#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

public class OpenAIAssistantFixture : AgentFixture
{
#pragma warning disable CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.
    private AssistantClient? _assistantClient;
    private Assistant? _assistant;
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

        List<ChatMessage> messages = new();
        await foreach (var agentMessage in this._assistantClient!.GetMessagesAsync(chatClientThread.Id, new() { Order = MessageCollectionOrder.Ascending }))
        {
            messages.Add(new()
            {
                Role = agentMessage.Role == MessageRole.User ? ChatRole.User : ChatRole.Assistant,
                Contents = new List<AIContent>()
                {
                    new TextContent(agentMessage.Content[0].Text ?? string.Empty)
                },
            });
        }

        return messages;
    }

    public override Task DeleteThreadAsync(AgentThread thread)
    {
        if (thread?.Id is not null)
        {
            return this._assistantClient!.DeleteThreadAsync(thread.Id);
        }

        return Task.CompletedTask;
    }

    public override async Task InitializeAsync()
    {
        var config = TestConfiguration.LoadSection<OpenAIConfiguration>();

        var client = new OpenAIClient(config.ApiKey);
        this._assistantClient = client.GetAssistantClient();

        this._assistant =
            await this._assistantClient.CreateAssistantAsync(
                config.ChatModelId!,
                new AssistantCreationOptions()
                {
                    Name = "HelpfulAssistant",
                    Instructions = "You are a helpful assistant."
                });

        this._chatClient = this._assistantClient.AsIChatClient(this._assistant.Id);

        this._agent = new ChatClientAgent(this._chatClient);
    }

    public override Task DisposeAsync()
    {
        if (this._assistantClient is not null && this._assistant is not null)
        {
            return this._assistantClient.DeleteAssistantAsync(this._assistant.Id);
        }

        return Task.CompletedTask;
    }
}
