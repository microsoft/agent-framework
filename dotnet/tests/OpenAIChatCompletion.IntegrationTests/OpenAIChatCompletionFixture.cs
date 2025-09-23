// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using OpenAI;
using Shared.IntegrationTests;

namespace OpenAIChatCompletion.IntegrationTests;

public class OpenAIChatCompletionFixture : IChatClientAgentFixture
{
    private static readonly OpenAIConfiguration s_config = TestConfiguration.LoadSection<OpenAIConfiguration>();
    private readonly bool _useReasoningModel;

    private ChatClientAgent _agent = null!;

    public OpenAIChatCompletionFixture(bool useReasoningChatModel)
    {
        this._useReasoningModel = useReasoningChatModel;
    }

    public AIAgent Agent => this._agent;

    public IChatClient ChatClient => this._agent.ChatClient;

    public async Task<List<ChatMessage>> GetChatHistoryAsync(AgentThread thread)
    {
        var typedThread = (ChatClientAgentThread)thread;

        return typedThread.MessageStore is null ? [] : (await typedThread.MessageStore.GetMessagesAsync()).ToList();
    }

    public Task<ChatClientAgent> CreateChatClientAgentAsync(
        string name = "HelpfulAssistant",
        string instructions = "You are a helpful assistant.",
        IList<AITool>? aiTools = null)
    {
        var chatClient = new OpenAIClient(s_config.ApiKey)
            .GetChatClient(this._useReasoningModel ? s_config.ChatReasoningModelId : s_config.ChatModelId)
            .AsIChatClient();

        return Task.FromResult(new ChatClientAgent(chatClient, options: new()
        {
            Name = name,
            Instructions = instructions,
            ChatOptions = new() { Tools = aiTools }
        }));
    }

    public Task DeleteAgentAsync(ChatClientAgent agent) =>
        // Chat Completion does not require/support deleting agents, so this is a no-op.
        Task.CompletedTask;

    public Task DeleteThreadAsync(AgentThread thread) =>
        // Chat Completion does not require/support deleting threads, so this is a no-op.
        Task.CompletedTask;

    public async Task InitializeAsync() =>
        this._agent = await this.CreateChatClientAgentAsync();

    public Task DisposeAsync() =>
        Task.CompletedTask;
}
