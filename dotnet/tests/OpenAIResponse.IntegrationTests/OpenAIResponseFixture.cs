// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;
using Shared.IntegrationTests;

namespace ResponseResult.IntegrationTests;

public class OpenAIResponseFixture(bool store) : IChatClientAgentFixture
{
    private ResponsesClient _openAIResponseClient = null!;
    private ChatClientAgent _agent = null!;

    public AIAgent Agent => this._agent;

    public IChatClient ChatClient => this._agent.ChatClient;

    public async Task<List<ChatMessage>> GetChatHistoryAsync(AIAgent agent, AgentSession session)
    {
        var typedSession = (ChatClientAgentSession)session;

        if (store)
        {
            var inputItems = await this._openAIResponseClient.GetResponseInputItemsAsync(typedSession.ConversationId).ToListAsync();
            var response = await this._openAIResponseClient.GetResponseAsync(typedSession.ConversationId);
            var responseItem = response.Value.OutputItems.FirstOrDefault()!;

            // Take the messages that were the chat history leading up to the current response
            // remove the instruction messages, and reverse the order so that the most recent message is last.
            var previousMessages = inputItems
                .Select(ConvertToChatMessage)
                .Where(x => x.Text != "You are a helpful assistant.")
                .Reverse();

            // Convert the response item to a chat message.
            var responseMessage = ConvertToChatMessage(responseItem);

            // Concatenate the previous messages with the response message to get a full chat history
            // that includes the current response.
            return [.. previousMessages, responseMessage];
        }

        var chatHistoryProvider = agent.GetService<ChatHistoryProvider>();

        if (chatHistoryProvider is null)
        {
            return [];
        }

        return (await chatHistoryProvider.InvokingAsync(new(agent, session, []))).ToList();
    }

    private static ChatMessage ConvertToChatMessage(ResponseItem item)
    {
        if (item is MessageResponseItem messageResponseItem)
        {
            var role = messageResponseItem.Role == MessageRole.User ? ChatRole.User : ChatRole.Assistant;
            return new ChatMessage(role, messageResponseItem.Content.FirstOrDefault()?.Text);
        }

        throw new NotSupportedException("This test currently only supports text messages");
    }

    public async Task<ChatClientAgent> CreateChatClientAgentAsync(
        string name = "HelpfulAssistant",
        string instructions = "You are a helpful assistant.",
        IList<AITool>? aiTools = null) =>
            new(
                this._openAIResponseClient.AsIChatClient(),
                options: new()
                {
                    Name = name,
                    ChatOptions = new ChatOptions
                    {
                        Instructions = instructions,
                        Tools = aiTools,
                        RawRepresentationFactory = new Func<IChatClient, object>(_ => new CreateResponseOptions() { StoredOutputEnabled = store })
                    },
                });

    public Task DeleteAgentAsync(ChatClientAgent agent) =>
        // Chat Completion does not require/support deleting agents, so this is a no-op.
        Task.CompletedTask;

    public Task DeleteSessionAsync(AgentSession session) =>
        // Chat Completion does not require/support deleting threads, so this is a no-op.
        Task.CompletedTask;

    public async Task InitializeAsync()
    {
        this._openAIResponseClient = new OpenAIClient(TestConfiguration.GetRequiredValue(TestSettings.OpenAIApiKey))
            .GetResponsesClient(TestConfiguration.GetRequiredValue(TestSettings.OpenAIChatModelName));

        this._agent = await this.CreateChatClientAgentAsync();
    }

    public Task DisposeAsync() => Task.CompletedTask;
}
