// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Assistants;
using Shared.IntegrationTests;

namespace OpenAIAssistant.IntegrationTests;

public class OpenAIAssistantFixture : IChatClientAgentFixture
{
    private AssistantClient? _assistantClient;
    private ChatClientAgent _agent = null!;

    public AIAgent Agent => this._agent;

    public IChatClient ChatClient => this._agent.ChatClient;

    public async Task<List<ChatMessage>> GetChatHistoryAsync(AIAgent agent, AgentSession session)
    {
        var typedSession = (ChatClientAgentSession)session;
        List<ChatMessage> messages = [];
        await foreach (var agentMessage in this._assistantClient!.GetMessagesAsync(typedSession.ConversationId, new() { Order = MessageCollectionOrder.Ascending }))
        {
            messages.Add(new()
            {
                Role = agentMessage.Role == MessageRole.User ? ChatRole.User : ChatRole.Assistant,
                Contents =
                [
                    new TextContent(agentMessage.Content[0].Text ?? string.Empty)
                ],
            });
        }

        return messages;
    }

    public async Task<ChatClientAgent> CreateChatClientAgentAsync(
        string name = "HelpfulAssistant",
        string instructions = "You are a helpful assistant.",
        IList<AITool>? aiTools = null)
    {
        var assistant =
            await this._assistantClient!.CreateAssistantAsync(
                TestConfiguration.GetRequiredValue(TestSettings.OpenAIChatModelName),
                new AssistantCreationOptions()
                {
                    Name = name,
                    Instructions = instructions
                });

        return new ChatClientAgent(
            this._assistantClient.AsIChatClient(assistant.Value.Id),
            options: new()
            {
                Id = assistant.Value.Id,
                ChatOptions = new() { Tools = aiTools }
            });
    }

    public Task DeleteAgentAsync(ChatClientAgent agent) =>
        this._assistantClient!.DeleteAssistantAsync(agent.Id);

    public Task DeleteSessionAsync(AgentSession session)
    {
        var typedSession = (ChatClientAgentSession)session;
        if (typedSession?.ConversationId is not null)
        {
            return this._assistantClient!.DeleteThreadAsync(typedSession.ConversationId);
        }

        return Task.CompletedTask;
    }

    public async Task InitializeAsync()
    {
        var client = new OpenAIClient(TestConfiguration.GetRequiredValue(TestSettings.OpenAIApiKey));
        this._assistantClient = client.GetAssistantClient();

        this._agent = await this.CreateChatClientAgentAsync();
    }

    public Task DisposeAsync()
    {
        if (this._assistantClient is not null && this._agent is not null)
        {
            return this._assistantClient.DeleteAssistantAsync(this._agent.Id);
        }

        return Task.CompletedTask;
    }
}
