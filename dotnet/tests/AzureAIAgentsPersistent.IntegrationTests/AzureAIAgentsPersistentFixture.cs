// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using AgentConformanceTests;
using Azure;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.AzureAIAgentsPersistent;
using Shared.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

public class AzureAIAgentsPersistentFixture : AgentFixture
{
#pragma warning disable CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.
    private Agent _agent;
    private PersistentAgentsClient _persistentAgentsClient;
    private PersistentAgent _persistentAgent;
#pragma warning restore CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.

    public override Agent Agent => this._agent;

    public override async Task<List<ChatMessage>> GetChatHistoryAsync(AgentThread thread)
    {
        if (thread is not ChatClientAgentThread chatClientThread)
        {
            throw new InvalidOperationException($"The thread must be of type {nameof(ChatClientAgentThread)} to retrieve chat history.");
        }

        List<ChatMessage> messages = [];

        AsyncPageable<PersistentThreadMessage> threadMessages = this._persistentAgentsClient.Messages.GetMessagesAsync(threadId: thread.Id, order: ListSortOrder.Ascending);

        await foreach (var threadMessage in threadMessages)
        {
            var message = new ChatMessage
            {
                Role = threadMessage.Role == MessageRole.User ? ChatRole.User : ChatRole.Assistant
            };

            foreach (var content in threadMessage.ContentItems)
            {
                if (content is MessageTextContent textContent)
                {
                    message.Contents.Add(new TextContent(textContent.Text));
                }
            }

            messages.Add(message);
        }

        return messages;
    }

    public override Task DeleteThreadAsync(AgentThread thread)
    {
        if (thread?.Id is not null)
        {
            return this._persistentAgentsClient.Threads.DeleteThreadAsync(thread.Id);
        }

        return Task.CompletedTask;
    }

    public override Task DisposeAsync()
    {
        if (this._persistentAgentsClient is not null && this._persistentAgent is not null)
        {
            return this._persistentAgentsClient.Administration.DeleteAgentAsync(this._persistentAgent.Id);
        }

        return Task.CompletedTask;
    }

    public override async Task InitializeAsync()
    {
        var config = TestConfiguration.LoadSection<AzureAIConfiguration>();

        this._persistentAgentsClient = new(config.Endpoint, new AzureCliCredential());

        var persistentAgentResponse = await this._persistentAgentsClient.Administration.CreateAgentAsync(
            model: config.DeploymentName,
            name: "HelpfulAssistant",
            instructions: "You are a helpful assistant.");

        this._persistentAgent = persistentAgentResponse.Value;

        var chatClient = this._persistentAgentsClient.AsIChatClient(this._persistentAgent.Id);

        this._agent = new ChatClientAgent(chatClient);
    }
}
