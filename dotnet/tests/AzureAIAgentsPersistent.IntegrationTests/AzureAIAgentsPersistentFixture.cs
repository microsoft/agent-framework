// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformance.IntegrationTests.Support;
using Azure;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Shared.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

public class AzureAIAgentsPersistentFixture : IChatClientAgentFixture
{
    private static readonly AzureAIConfiguration s_config = TestConfiguration.LoadSection<AzureAIConfiguration>();

#pragma warning disable CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.
    private ChatClientAgent _agent;
    private PersistentAgentsClient _persistentAgentsClient;
#pragma warning restore CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.

    public IChatClient ChatClient => this._agent.ChatClient;

    public AIAgent Agent => this._agent;

    public async Task<List<ChatMessage>> GetChatHistoryAsync(AgentThread thread)
    {
        List<ChatMessage> messages = [];

        AsyncPageable<PersistentThreadMessage> threadMessages = this._persistentAgentsClient.Messages.GetMessagesAsync(threadId: thread.ConversationId, order: ListSortOrder.Ascending);

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

    public async Task<ChatClientAgent> CreateChatClientAgentAsync(
        string name = "HelpfulAssistant",
        string instructions = "You are a helpful assistant.",
        IList<AITool>? aiTools = null)
    {
        var persistentAgentResponse = await this._persistentAgentsClient.Administration.CreateAgentAsync(
            model: s_config.DeploymentName,
            name: name,
            instructions: instructions);

        var persistentAgent = persistentAgentResponse.Value;

        return new ChatClientAgent(
            this._persistentAgentsClient.AsIChatClient(persistentAgent.Id),
            options: new()
            {
                Id = persistentAgent.Id,
                ChatOptions = new() { Tools = aiTools }
            });
    }

    public Task DeleteAgentAsync(ChatClientAgent agent)
    {
        return this._persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
    }

    public Task DeleteThreadAsync(AgentThread thread)
    {
        if (thread?.ConversationId is not null)
        {
            return this._persistentAgentsClient.Threads.DeleteThreadAsync(thread.ConversationId);
        }

        return Task.CompletedTask;
    }

    public Task DisposeAsync()
    {
        if (this._persistentAgentsClient is not null && this._agent is not null)
        {
            return this._persistentAgentsClient.Administration.DeleteAgentAsync(this._agent.Id);
        }

        return Task.CompletedTask;
    }

    public async Task InitializeAsync()
    {
        this._persistentAgentsClient = new(s_config.Endpoint, new AzureCliCredential());
        this._agent = await this.CreateChatClientAgentAsync();
    }
}
