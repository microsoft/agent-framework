// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests;
using AgentConformance.IntegrationTests.Support;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Extensions.AI;
using OpenAI.Responses;
using Shared.IntegrationTests;

namespace Foundry.IntegrationTests;

/// <summary>
/// Integration test fixture that creates versioned Foundry agents via
/// <c>AIProjectClient.AgentAdministrationClient.CreateAgentVersionAsync</c> and wraps them
/// with <c>AIProjectClient.AsAIAgent(ProjectsAgentVersion)</c>.
/// </summary>
public class FoundryVersionedAgentFixture : IChatClientAgentFixture
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
        var chatClientSession = (ChatClientAgentSession)session;

        if (chatClientSession.ConversationId?.StartsWith("conv_", StringComparison.OrdinalIgnoreCase) == true)
        {
            return await this.GetChatHistoryFromConversationAsync(chatClientSession.ConversationId);
        }

        if (chatClientSession.ConversationId?.StartsWith("resp_", StringComparison.OrdinalIgnoreCase) == true)
        {
            return await this.GetChatHistoryFromResponsesChainAsync(chatClientSession.ConversationId);
        }

        var chatHistoryProvider = agent.GetService<ChatHistoryProvider>();

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
        var definition = new DeclarativeAgentDefinition(TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName))
        {
            Instructions = instructions
        };

        // Register AIFunction tool definitions in the server-side agent definition so the model
        // can invoke them. The local AIFunction implementations are matched by name via AsAIAgent.
        if (aiTools is not null)
        {
            foreach (var tool in aiTools)
            {
                if (tool.AsOpenAIResponseTool() is ResponseTool responseTool)
                {
                    definition.Tools.Add(responseTool);
                }
            }
        }

        var agentVersion = await this._client.AgentAdministrationClient.CreateAgentVersionAsync(
            GenerateUniqueAgentName(name),
            new ProjectsAgentVersionCreationOptions(definition));

        return this._client.AsAIAgent(agentVersion, tools: aiTools).GetService<ChatClientAgent>()!;
    }

    public async Task<ChatClientAgent> CreateChatClientAgentAsync(ChatClientAgentOptions options)
    {
        options.Name ??= GenerateUniqueAgentName("HelpfulAssistant");

        var definition = new DeclarativeAgentDefinition(
            options.ChatOptions?.ModelId ?? TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName))
        {
            Instructions = options.ChatOptions?.Instructions
        };

        var agentVersion = await this._client.AgentAdministrationClient.CreateAgentVersionAsync(
            options.Name,
            new ProjectsAgentVersionCreationOptions(definition) { Description = options.Description });

        var agent = this._client.AsAIAgent(agentVersion, tools: options.ChatOptions?.Tools);

        return agent.GetService<ChatClientAgent>()!;
    }

    public static string GenerateUniqueAgentName(string baseName) =>
        $"{baseName}-{Guid.NewGuid().ToString("N").Substring(0, 8)}";

    public Task DeleteAgentAsync(ChatClientAgent agent) =>
        this._client.AgentAdministrationClient.DeleteAgentAsync(agent.Name);

    public async Task DeleteSessionAsync(AgentSession session)
    {
        var typedSession = (ChatClientAgentSession)session;
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

    public ValueTask DisposeAsync()
    {
        GC.SuppressFinalize(this);

        if (this._client is not null && this._agent is not null)
        {
            return new ValueTask(this._client.AgentAdministrationClient.DeleteAgentAsync(this._agent.Name));
        }

        return default;
    }

    public virtual async ValueTask InitializeAsync()
    {
        this._client = new(new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint)), TestAzureCliCredentials.CreateAzureCliCredential());

        var agentVersion = await this._client.AgentAdministrationClient.CreateAgentVersionAsync(
            GenerateUniqueAgentName("HelpfulAssistant"),
            new ProjectsAgentVersionCreationOptions(
                new DeclarativeAgentDefinition(TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName))
                {
                    Instructions = "You are a helpful assistant."
                }));

        this._agent = this._client.AsAIAgent(agentVersion);
    }

    public async Task InitializeAsync(ChatClientAgentOptions options)
    {
        this._client = new(new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint)), TestAzureCliCredentials.CreateAzureCliCredential());
        options.Name ??= GenerateUniqueAgentName("HelpfulAssistant");

        var definition = new DeclarativeAgentDefinition(
            options.ChatOptions?.ModelId ?? TestConfiguration.GetRequiredValue(TestSettings.AzureAIModelDeploymentName))
        {
            Instructions = options.ChatOptions?.Instructions
        };

        var agentVersion = await this._client.AgentAdministrationClient.CreateAgentVersionAsync(
            options.Name,
            new ProjectsAgentVersionCreationOptions(definition) { Description = options.Description });

        this._agent = this._client.AsAIAgent(agentVersion, tools: options.ChatOptions?.Tools);
    }
}
