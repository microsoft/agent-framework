// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformance.IntegrationTests.Support;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;
using Shared.IntegrationTests;

namespace AzureAI.IntegrationTests;

/// <summary>
/// Integration test fixture that creates non-versioned Responses agents via the direct <c>AIProjectClient.AsAIAgent(...)</c> path.
/// </summary>
public class ResponsesAgentFixture : IChatClientAgentFixture
{
    private FoundryAgent _agent = null!;
    private AIProjectClient _client = null!;

    public IChatClient ChatClient => this._agent.GetService<ChatClientAgent>()!.ChatClient;

    public AIAgent Agent => this._agent;

    public async Task<string> CreateConversationAsync()
    {
        var response = await this._client.GetProjectOpenAIClient().GetProjectConversationsClient().CreateProjectConversationAsync();
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
        var openAIResponseClient = this._client.GetProjectOpenAIClient().GetProjectResponsesClient();
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
        List<ChatMessage> messages = [];
        await foreach (AgentResponseItem item in this._client.GetProjectOpenAIClient().GetProjectConversationsClient().GetProjectConversationItemsAsync(conversationId, order: "asc"))
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
        return Task.FromResult(this._client.AsAIAgent(
            model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
            instructions: instructions,
            name: name,
            tools: aiTools).GetService<ChatClientAgent>()!);
    }

    public Task<ChatClientAgent> CreateChatClientAgentAsync(ChatClientAgentOptions options)
    {
        return Task.FromResult(this._client.AsAIAgent(options).GetService<ChatClientAgent>()!);
    }

    // Non-versioned Responses agents have no server-side agent to delete.
    public Task DeleteAgentAsync(ChatClientAgent agent) => Task.CompletedTask;

    public async Task DeleteSessionAsync(AgentSession session)
    {
        ChatClientAgentSession typedSession = (ChatClientAgentSession)session;

        if (typedSession.ConversationId?.StartsWith("conv_", StringComparison.OrdinalIgnoreCase) == true)
        {
            await this._client.GetProjectOpenAIClient().GetProjectConversationsClient().DeleteConversationAsync(typedSession.ConversationId);
        }
        else if (typedSession.ConversationId?.StartsWith("resp_", StringComparison.OrdinalIgnoreCase) == true)
        {
            await this.DeleteResponseChainAsync(typedSession.ConversationId!);
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

    // Non-versioned Responses agents have no server-side agent to clean up on dispose.
    public ValueTask DisposeAsync()
    {
        GC.SuppressFinalize(this);
        return default;
    }

    public virtual ValueTask InitializeAsync()
    {
        this._client = new AIProjectClient(
            new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint)),
            TestAzureCliCredentials.CreateAzureCliCredential());

        this._agent = this._client.AsAIAgent(
            model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
            instructions: "You are a helpful assistant.",
            name: "HelpfulAssistant");

        return default;
    }

    public ValueTask InitializeAsync(ChatClientAgentOptions options)
    {
        this._client = new AIProjectClient(
            new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint)),
            TestAzureCliCredentials.CreateAzureCliCredential());

        this._agent = this._client.AsAIAgent(options);

        return default;
    }
}
