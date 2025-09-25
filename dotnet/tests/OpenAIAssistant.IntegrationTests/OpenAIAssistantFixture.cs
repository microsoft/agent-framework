// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using OpenAI;
using OpenAI.Assistants;
using Shared.IntegrationTests;

namespace OpenAIAssistant.IntegrationTests;

public class OpenAIAssistantFixture : IChatClientAgentFixture
{
    private static readonly OpenAIConfiguration s_config = TestConfiguration.LoadSection<OpenAIConfiguration>();

    private AssistantClient? _assistantClient;
    private ChatClientAgent _agent = null!;

    public AIAgent Agent => this._agent;

    public IChatClient ChatClient => this._agent.ChatClient;

    public async Task<List<ChatMessage>> GetChatHistoryAsync(AgentThread thread)
    {
        var typedThread = (ChatClientAgentThread)thread;
        List<ChatMessage> messages = [];
        await foreach (var agentMessage in this._assistantClient!.GetMessagesAsync(typedThread.ConversationId, new() { Order = MessageCollectionOrder.Ascending }))
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
                s_config.ChatModelId!,
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

    public Task DeleteThreadAsync(AgentThread thread)
    {
        var typedThread = (ChatClientAgentThread)thread;
        if (typedThread?.ConversationId is not null)
        {
            return this._assistantClient!.DeleteThreadAsync(typedThread.ConversationId);
        }

        return Task.CompletedTask;
    }

    public async Task InitializeAsync()
    {
        var client = new OpenAIClient(s_config.ApiKey);
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
