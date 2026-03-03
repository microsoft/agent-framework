// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformance.IntegrationTests.Support;
using Azure;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Shared.IntegrationTests;

namespace AzureAIAgentsPersistent.IntegrationTests;

public class AzureAIAgentsPersistentFixture : IChatClientAgentFixture
{
    private ChatClientAgent _agent = null!;
    private PersistentAgentsClient _persistentAgentsClient = null!;

    public IChatClient ChatClient => this._agent.ChatClient;

    public AIAgent Agent => this._agent;

    public async Task<List<ChatMessage>> GetChatHistoryAsync(AIAgent agent, AgentSession session)
    {
        List<ChatMessage> messages = [];
        var typedSession = (ChatClientAgentSession)session;

        await foreach (var threadMessage in (AsyncPageable<PersistentThreadMessage>)this._persistentAgentsClient.Messages.GetMessagesAsync(
            threadId: typedSession.ConversationId, order: ListSortOrder.Ascending))
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
            model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
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

    public Task DeleteAgentAsync(ChatClientAgent agent) =>
        this._persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);

    public Task DeleteSessionAsync(AgentSession session)
    {
        var typedSession = (ChatClientAgentSession)session;
        if (typedSession?.ConversationId is not null)
        {
            return this._persistentAgentsClient.Threads.DeleteThreadAsync(typedSession.ConversationId);
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
        this._persistentAgentsClient = new(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint), new AzureCliCredential());
        this._agent = await this.CreateChatClientAgentAsync();
    }
}
