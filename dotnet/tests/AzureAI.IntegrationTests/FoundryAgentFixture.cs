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
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;
using Shared.IntegrationTests;

namespace AzureAI.IntegrationTests;

/// <summary>
/// Integration test fixture that creates agents via the <see cref="FoundryAgent"/> constructor (Responses API, no server-side agent).
/// </summary>
public class FoundryAgentFixture : IChatClientAgentFixture
{
    private FoundryAgent _agent = null!;

    public IChatClient ChatClient => this._agent.GetService<ChatClientAgent>()!.ChatClient;

    public AIAgent Agent => this._agent;

    public async Task<string> CreateConversationAsync()
    {
        AIProjectClient client = this._agent.GetService<AIProjectClient>()!;
        var response = await client.GetProjectOpenAIClient().GetProjectConversationsClient().CreateProjectConversationAsync();
        return response.Value.Id;
    }

    public async Task<List<ChatMessage>> GetChatHistoryAsync(AIAgent agent, AgentSession session)
    {
        ChatClientAgentSession chatClientSession = (ChatClientAgentSession)session;

        if (chatClientSession.ConversationId?.StartsWith("conv_", StringComparison.OrdinalIgnoreCase) == true)
        {
            return await this.GetChatHistoryFromConversationAsync(chatClientSession.ConversationId);
        }

        if (chatClientSession.ConversationId?.StartsWith("resp_", StringComparison.OrdinalIgnoreCase) == true)
        {
            return await this.GetChatHistoryFromResponsesChainAsync(chatClientSession.ConversationId);
        }

        ChatHistoryProvider? chatHistoryProvider = agent.GetService<ChatHistoryProvider>();

        if (chatHistoryProvider is null)
        {
            return [];
        }

        return (await chatHistoryProvider.InvokingAsync(new(agent, session, []))).ToList();
    }

    private async Task<List<ChatMessage>> GetChatHistoryFromResponsesChainAsync(string conversationId)
    {
        AIProjectClient client = this._agent.GetService<AIProjectClient>()!;
        var openAIResponseClient = client.GetProjectOpenAIClient().GetProjectResponsesClient();
        var inputItems = await openAIResponseClient.GetResponseInputItemsAsync(conversationId).ToListAsync();
        var response = await openAIResponseClient.GetResponseAsync(conversationId);
        ResponseItem responseItem = response.Value.OutputItems.FirstOrDefault()!;

        var previousMessages = inputItems
            .Select(ConvertToChatMessage)
            .Where(x => x.Text != "You are a helpful assistant.")
            .Reverse();

        ChatMessage responseMessage = ConvertToChatMessage(responseItem);

        return [.. previousMessages, responseMessage];
    }

    private static ChatMessage ConvertToChatMessage(ResponseItem item)
    {
        if (item is MessageResponseItem messageResponseItem)
        {
            ChatRole role = messageResponseItem.Role == MessageRole.User ? ChatRole.User : ChatRole.Assistant;
            return new ChatMessage(role, messageResponseItem.Content.FirstOrDefault()?.Text);
        }

        throw new NotSupportedException("This test currently only supports text messages");
    }

    private async Task<List<ChatMessage>> GetChatHistoryFromConversationAsync(string conversationId)
    {
        AIProjectClient client = this._agent.GetService<AIProjectClient>()!;
        List<ChatMessage> messages = [];
        await foreach (AgentResponseItem item in client.GetProjectOpenAIClient().GetProjectConversationsClient().GetProjectConversationItemsAsync(conversationId, order: "asc"))
        {
            var openAIItem = item.AsResponseResultItem();
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

    public Task<ChatClientAgent> CreateChatClientAgentAsync(
        string name = "HelpfulAssistant",
        string instructions = "You are a helpful assistant.",
        IList<AITool>? aiTools = null)
    {
        FoundryAgent agent = new(
            new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint)),
            new DefaultAzureCredential(),
            model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
            instructions: instructions,
            name: name,
            tools: aiTools);

        return Task.FromResult(agent.GetService<ChatClientAgent>()!);
    }

    public Task<ChatClientAgent> CreateChatClientAgentAsync(ChatClientAgentOptions options)
    {
        FoundryAgent agent = new(
            new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint)),
            new DefaultAzureCredential(),
            options: options);

        return Task.FromResult(agent.GetService<ChatClientAgent>()!);
    }

    // FoundryAgent has no server-side agent to delete.
    public Task DeleteAgentAsync(ChatClientAgent agent) => Task.CompletedTask;

    public async Task DeleteSessionAsync(AgentSession session)
    {
        ChatClientAgentSession typedSession = (ChatClientAgentSession)session;
        AIProjectClient client = this._agent.GetService<AIProjectClient>()!;

        if (typedSession.ConversationId?.StartsWith("conv_", StringComparison.OrdinalIgnoreCase) == true)
        {
            await client.GetProjectOpenAIClient().GetProjectConversationsClient().DeleteConversationAsync(typedSession.ConversationId);
        }
        else if (typedSession.ConversationId?.StartsWith("resp_", StringComparison.OrdinalIgnoreCase) == true)
        {
            await this.DeleteResponseChainAsync(typedSession.ConversationId!);
        }
    }

    private async Task DeleteResponseChainAsync(string lastResponseId)
    {
        AIProjectClient client = this._agent.GetService<AIProjectClient>()!;
        var response = await client.GetProjectOpenAIClient().GetProjectResponsesClient().GetResponseAsync(lastResponseId);
        await client.GetProjectOpenAIClient().GetProjectResponsesClient().DeleteResponseAsync(lastResponseId);

        if (response.Value.PreviousResponseId is not null)
        {
            await this.DeleteResponseChainAsync(response.Value.PreviousResponseId);
        }
    }

    // FoundryAgent has no server-side agent to clean up on dispose.
    public ValueTask DisposeAsync()
    {
        GC.SuppressFinalize(this);
        return default;
    }

    public virtual ValueTask InitializeAsync()
    {
        this._agent = new FoundryAgent(
            new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint)),
            new DefaultAzureCredential(),
            model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
            instructions: "You are a helpful assistant.",
            name: "HelpfulAssistant");

        return default;
    }

    public ValueTask InitializeAsync(ChatClientAgentOptions options)
    {
        this._agent = new FoundryAgent(
            new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint)),
            new DefaultAzureCredential(),
            options: options);

        return default;
    }
}
