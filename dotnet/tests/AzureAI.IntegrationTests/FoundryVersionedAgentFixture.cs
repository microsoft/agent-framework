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
/// Integration test fixture that creates agents via <see cref="FoundryVersionedAgent"/> factory methods.
/// </summary>
public class FoundryVersionedAgentFixture : IChatClientAgentFixture
{
    private FoundryVersionedAgent _agent = null!;

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

    public async Task<ChatClientAgent> CreateChatClientAgentAsync(
        string name = "HelpfulAssistant",
        string instructions = "You are a helpful assistant.",
        IList<AITool>? aiTools = null)
    {
        FoundryVersionedAgent agent = await FoundryVersionedAgent.CreateAIAgentAsync(
            new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint)),
            new DefaultAzureCredential(),
            GenerateUniqueAgentName(name),
            model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
            instructions: instructions,
            tools: aiTools);

        return agent.GetService<ChatClientAgent>()!;
    }

    public async Task<ChatClientAgent> CreateChatClientAgentAsync(ChatClientAgentOptions options)
    {
        options.Name ??= GenerateUniqueAgentName("HelpfulAssistant");

        FoundryVersionedAgent agent = await FoundryVersionedAgent.CreateAIAgentAsync(
            new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint)),
            new DefaultAzureCredential(),
            model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
            options: options);

        return agent.GetService<ChatClientAgent>()!;
    }

    public static string GenerateUniqueAgentName(string baseName) =>
        $"{baseName}-{Guid.NewGuid().ToString("N").Substring(0, 8)}";

    public Task DeleteAgentAsync(ChatClientAgent agent)
    {
        AIProjectClient client = this._agent.GetService<AIProjectClient>()!;
        return client.Agents.DeleteAgentAsync(agent.Name);
    }

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

    public ValueTask DisposeAsync()
    {
        GC.SuppressFinalize(this);

        if (this._agent is not null)
        {
            return new ValueTask(FoundryVersionedAgent.DeleteAIAgentAsync(this._agent));
        }

        return default;
    }

    public virtual async ValueTask InitializeAsync()
    {
        this._agent = await FoundryVersionedAgent.CreateAIAgentAsync(
            new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint)),
            new DefaultAzureCredential(),
            GenerateUniqueAgentName("HelpfulAssistant"),
            model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
            instructions: "You are a helpful assistant.");
    }

    public async Task InitializeAsync(ChatClientAgentOptions options)
    {
        options.Name ??= GenerateUniqueAgentName("HelpfulAssistant");

        this._agent = await FoundryVersionedAgent.CreateAIAgentAsync(
            new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint)),
            new DefaultAzureCredential(),
            model: TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName),
            options: options);
    }
}
