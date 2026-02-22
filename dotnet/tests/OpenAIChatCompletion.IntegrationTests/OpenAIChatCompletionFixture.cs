// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using Shared.IntegrationTests;

namespace OpenAIChatCompletion.IntegrationTests;

public class OpenAIChatCompletionFixture : IChatClientAgentFixture
{
    private readonly bool _useReasoningModel;

    private ChatClientAgent _agent = null!;

    public OpenAIChatCompletionFixture(bool useReasoningChatModel)
    {
        this._useReasoningModel = useReasoningChatModel;
    }

    public AIAgent Agent => this._agent;

    public IChatClient ChatClient => this._agent.ChatClient;

    public async Task<List<ChatMessage>> GetChatHistoryAsync(AIAgent agent, AgentSession session)
    {
        var chatHistoryProvider = agent.GetService<ChatHistoryProvider>();

        if (chatHistoryProvider is null)
        {
            return [];
        }

        return (await chatHistoryProvider.InvokingAsync(new(agent, session, []))).ToList();
    }

    public Task<ChatClientAgent> CreateChatClientAgentAsync(
        string name = "HelpfulAssistant",
        string instructions = "You are a helpful assistant.",
        IList<AITool>? aiTools = null)
    {
        var chatClient = new OpenAIClient(TestConfiguration.GetRequiredValue(TestSettings.OpenAIApiKey))
            .GetChatClient(this._useReasoningModel ? TestConfiguration.GetRequiredValue(TestSettings.OpenAIReasoningModelName) : TestConfiguration.GetRequiredValue(TestSettings.OpenAIChatModelName))
            .AsIChatClient();

        return Task.FromResult(new ChatClientAgent(chatClient, options: new()
        {
            Name = name,
            ChatOptions = new() { Instructions = instructions, Tools = aiTools }
        }));
    }

    public Task DeleteAgentAsync(ChatClientAgent agent) =>
        // Chat Completion does not require/support deleting agents, so this is a no-op.
        Task.CompletedTask;

    public Task DeleteSessionAsync(AgentSession session) =>
        // Chat Completion does not require/support deleting threads, so this is a no-op.
        Task.CompletedTask;

    public async Task InitializeAsync() =>
        this._agent = await this.CreateChatClientAgentAsync();

    public Task DisposeAsync() =>
        Task.CompletedTask;
}
