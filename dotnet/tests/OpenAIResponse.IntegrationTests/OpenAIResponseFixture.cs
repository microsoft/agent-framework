// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using AgentConformanceTests;
using Microsoft.Agents;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;
using Shared.IntegrationTests;

namespace OpenAIResponse.IntegrationTests;

public class OpenAIResponseFixture(bool store) : AgentFixture
{
#pragma warning disable CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.
    private OpenAIResponseClient _openAIResponseClient;
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
            return previousMessages
                .Concat([responseMessage])
                .ToList();
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

    public override Task DeleteThreadAsync(AgentThread thread)
    {
        // Chat Completion does not require/support deleting threads, so this is a no-op.
        return Task.CompletedTask;
    }

    public override Task InitializeAsync()
    {
        var config = TestConfiguration.LoadSection<OpenAIConfiguration>();

        this._openAIResponseClient = new OpenAIClient(config.ApiKey)
            .GetOpenAIResponseClient(config.ChatModelId);
        this._chatClient = this._openAIResponseClient
            .AsIChatClient();

        var options = new ChatClientAgentOptions
        {
            Name = "HelpfulAssistant",
            Instructions = "You are a helpful assistant.",
            ChatOptions = new ChatOptions
            {
                RawRepresentationFactory = new Func<IChatClient, object>((_) => new ResponseCreationOptions() { StoredOutputEnabled = store })
            },
        };

        this._agent =
            new ChatClientAgent(this._chatClient, options);

        return Task.CompletedTask;
    }

    public override Task DisposeAsync()
    {
        this._chatClient.Dispose();
        return Task.CompletedTask;
    }
}
