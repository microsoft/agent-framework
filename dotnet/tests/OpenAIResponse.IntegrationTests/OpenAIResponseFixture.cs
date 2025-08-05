// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using OpenAI;
using OpenAI.Responses;
using Shared.IntegrationTests;

namespace OpenAIResponse.IntegrationTests;

public class OpenAIResponseFixture(bool store) : IChatClientAgentFixture
{
    private static readonly OpenAIConfiguration s_config = TestConfiguration.LoadSection<OpenAIConfiguration>();

#pragma warning disable CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.
    private OpenAIResponseClient _openAIResponseClient;
    private ChatClientAgent _agent;
#pragma warning restore CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.

    public AIAgent Agent => this._agent;

    public IChatClient ChatClient => this._agent.ChatClient;

    public async Task<List<ChatMessage>> GetChatHistoryAsync(AgentThread thread)
    {
        if (thread is not ChatClientAgentThread chatClientThread)
        {
            throw new InvalidOperationException("The thread must be of type ChatClientAgentThread to retrieve chat history.");
        }

        if (store)
        {
            var inputItems = await this._openAIResponseClient.GetResponseInputItemsAsync(chatClientThread.Id).ToListAsync();
            var response = await this._openAIResponseClient.GetResponseAsync(chatClientThread.Id);
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

        return await chatClientThread.GetMessagesAsync().ToListAsync();
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

    public Task<ChatClientAgent> CreateChatClientAgentAsync(
        string name = "HelpfulAssistant",
        string instructions = "You are a helpful assistant.",
        IList<AITool>? aiTools = null)
    {
        return Task.FromResult(new ChatClientAgent(
            this._openAIResponseClient.AsIChatClient(),
            options: new()
            {
                Name = name,
                Instructions = instructions,
                ChatOptions = new ChatOptions
                {
                    Tools = aiTools,
                    RawRepresentationFactory = new Func<IChatClient, object>((_) => new ResponseCreationOptions() { StoredOutputEnabled = store })
                },
            }));
    }

    public Task DeleteAgentAsync(ChatClientAgent agent)
    {
        // Chat Completion does not require/support deleting agents, so this is a no-op.
        return Task.CompletedTask;
    }

    public Task DeleteThreadAsync(AgentThread thread)
    {
        // Chat Completion does not require/support deleting threads, so this is a no-op.
        return Task.CompletedTask;
    }

    public async Task InitializeAsync()
    {
        this._openAIResponseClient = new OpenAIClient(s_config.ApiKey)
            .GetOpenAIResponseClient(s_config.ChatModelId);

        this._agent = await this.CreateChatClientAgentAsync();
    }

    public Task DisposeAsync()
    {
        return Task.CompletedTask;
    }
}
