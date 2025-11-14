// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformance.IntegrationTests.Support;
using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;
using Shared.IntegrationTests;

namespace AzureAI.IntegrationTests;

public class AIProjectClientFixture : IChatClientAgentFixture
{
    private static readonly AzureAIConfiguration s_config = TestConfiguration.LoadSection<AzureAIConfiguration>();

    private ChatClientAgent _agent = null!;
    private AIProjectClient _client = null!;

    public IChatClient ChatClient => this._agent.ChatClient;

    public AIAgent Agent => this._agent;

    public async Task<string> CreateConversationAsync()
    {
        var response = await this._client.GetProjectOpenAIClient().GetProjectConversationsClient().CreateProjectConversationAsync();
        return response.Value.Id;
    }

    public async Task<List<ChatMessage>> GetChatHistoryAsync(AgentThread thread)
    {
        var chatClientThread = (ChatClientAgentThread)thread;

        if (chatClientThread.ConversationId?.StartsWith("conv_", StringComparison.OrdinalIgnoreCase) == true)
        {
            // Conversation threads do not persist message history.
            return await this.GetChatHistoryFromConversationAsync(chatClientThread.ConversationId);
        }

        if (chatClientThread.ConversationId?.StartsWith("resp_", StringComparison.OrdinalIgnoreCase) == true)
        {
            return await this.GetChatHistoryFromResponsesChainAsync(chatClientThread.ConversationId);
        }

        return chatClientThread.MessageStore is null ? [] : (await chatClientThread.MessageStore.GetMessagesAsync()).ToList();
    }

    private async Task<List<ChatMessage>> GetChatHistoryFromResponsesChainAsync(string conversationId)
    {
        var openAIResponseClient = this._client.GetProjectOpenAIClient().GetProjectResponsesClient();
        var inputItems = await openAIResponseClient.GetResponseInputItemsAsync(conversationId).ToListAsync();
        var response = await openAIResponseClient.GetResponseAsync(conversationId);
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

    private static ChatMessage ConvertToChatMessage(ResponseItem item)
    {
        if (item is MessageResponseItem messageResponseItem)
        {
            var role = messageResponseItem.Role == MessageRole.User ? ChatRole.User : ChatRole.Assistant;
            return new ChatMessage(role, messageResponseItem.Content.FirstOrDefault()?.Text);
        }

        throw new NotSupportedException("This test currently only supports text messages");
    }

    private async Task<List<ChatMessage>> GetChatHistoryFromConversationAsync(string conversationId)
    {
        List<ChatMessage> messages = [];
        await foreach (AgentResponseItem item in this._client.GetProjectOpenAIClient().GetProjectConversationsClient().GetProjectConversationItemsAsync(conversationId, order: "asc"))
        {
            var openAIItem = item.AsOpenAIResponseItem();
            if (openAIItem is MessageResponseItem messageItem)
            {
                messages.Add(new ChatMessage
                {
                    Role = new ChatRole(messageItem.Role.ToString()),
                    Contents = messageItem.Content
                        .Where(c => c.Kind is ResponseContentPartKind.OutputText or ResponseContentPartKind.InputText)
                        .Select(c => new TextContent(c.Text))
                        .ToList<AIContent>()
                });
            }
        }

        return messages;
    }

    public async Task<ChatClientAgent> CreateChatClientAgentAsync(
        string name = "HelpfulAssistant",
        string instructions = "You are a helpful assistant.",
        IList<AITool>? aiTools = null)
    {
        return await this._client.CreateAIAgentAsync(GenerateUniqueAgentName(name), model: s_config.DeploymentName, instructions: instructions, tools: aiTools);
    }

    private static string GenerateUniqueAgentName(string baseName) =>
        $"{baseName}-{Guid.NewGuid().ToString("N").Substring(0, 8)}";

    public Task DeleteAgentAsync(ChatClientAgent agent) =>
        this._client.Agents.DeleteAgentAsync(agent.Name);

    public async Task DeleteThreadAsync(AgentThread thread)
    {
        var typedThread = (ChatClientAgentThread)thread;
        if (typedThread.ConversationId?.StartsWith("conv_", StringComparison.OrdinalIgnoreCase) == true)
        {
            await this._client.GetProjectOpenAIClient().GetProjectConversationsClient().DeleteConversationAsync(typedThread.ConversationId);
        }
        else if (typedThread.ConversationId?.StartsWith("resp_", StringComparison.OrdinalIgnoreCase) == true)
        {
            await this.DeleteResponseChainAsync(typedThread.ConversationId!);
        }
    }

    private async Task DeleteResponseChainAsync(string lastResponseId)
    {
        var response = await this._client.GetProjectOpenAIClient().GetProjectResponsesClient().GetResponseAsync(lastResponseId);
        await this._client.GetProjectOpenAIClient().GetProjectResponsesClient().DeleteResponseAsync(lastResponseId);

        if (response.Value.PreviousResponseId is not null)
        {
            await this.DeleteResponseChainAsync(response.Value.PreviousResponseId);
        }
    }

    public Task DisposeAsync()
    {
        if (this._client is not null && this._agent is not null)
        {
            return this._client.Agents.DeleteAgentAsync(this._agent.Name);
        }

        return Task.CompletedTask;
    }

    public async Task InitializeAsync()
    {
        this._client = new(new Uri(s_config.Endpoint), new AzureCliCredential());
        this._agent = await this.CreateChatClientAgentAsync();
    }
}
