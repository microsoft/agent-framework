// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using Azure.AI.Agents.Persistent;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.AzureAIAgentsPersistent;
using Microsoft.Shared.Samples;
using OpenAI;
using OpenAI.Assistants;
using OpenAI.Responses;

#pragma warning disable OPENAI001

namespace GettingStarted;

public class AgentSample(ITestOutputHelper output) : BaseSample(output)
{
    private const string AgentName = "HelpfulAssistant";
    private const string AgentInstructions = "You are a helpful assistant.";

    /// <summary>
    /// Represents the available providers for <see cref="IChatClient"/> instances.
    /// </summary>
    public enum ChatClientProviders
    {
        AzureOpenAI,
        OpenAIChatCompletion,
        OpenAIAssistant,
        OpenAIResponses,
        OpenAIResponses_InMemoryMessage,
        OpenAIResponses_ConversationId,
        AzureAIPersistentAgent
    }

    protected async Task<IChatClient> GetChatClientAsync(ChatClientProviders provider)
        => provider switch
        {
            ChatClientProviders.AzureOpenAI => GetAzureOpenAIChatClient(),
            ChatClientProviders.OpenAIChatCompletion => GetOpenAIChatClient(),
            ChatClientProviders.OpenAIAssistant => await GetOpenAIAssistantChatClientAsync(),
            ChatClientProviders.AzureAIPersistentAgent => await GetAzureAIPersistentAgentChatClientAsync(),
            ChatClientProviders.OpenAIResponses or
            ChatClientProviders.OpenAIResponses_InMemoryMessage or
            ChatClientProviders.OpenAIResponses_ConversationId
            => GetOpenAIResponsesClient(),
            _ => throw new NotSupportedException($"Provider {provider} is not supported.")
        };

    protected ChatOptions? GetChatOptions(ChatClientProviders? provider)
        => provider switch
        {
            ChatClientProviders.OpenAIResponses_InMemoryMessage => new() { RawRepresentationFactory = static (_) => new ResponseCreationOptions() { StoredOutputEnabled = false } },
            ChatClientProviders.OpenAIResponses_ConversationId => new() { RawRepresentationFactory = static (_) => new ResponseCreationOptions() { StoredOutputEnabled = true } },
            _ => null
        };

    protected OpenAIClient OpenAIClient => new(TestConfiguration.OpenAI.ApiKey);

    protected PersistentAgentsClient AzureAIPersistentAgentsClient => new(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

    private async Task<IChatClient> GetOpenAIAssistantChatClientAsync()
    {
        var assistantClient = OpenAIClient.GetAssistantClient();

        Assistant assistant = await assistantClient.CreateAssistantAsync(
            TestConfiguration.OpenAI.ChatModelId,
            new()
            {
                Name = AgentName,
                Instructions = AgentInstructions
            });

        return assistantClient.AsIChatClient(assistant.Id);
    }

    private async Task<IChatClient> GetAzureAIPersistentAgentChatClientAsync()
    {
        var persistentAgentsClient = new PersistentAgentsClient(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

        PersistentAgent persistentAgent = await persistentAgentsClient.Administration.CreateAgentAsync(
            model: TestConfiguration.AzureAI.DeploymentName,
            name: AgentName,
            instructions: AgentInstructions);

        return persistentAgentsClient.AsIChatClient(persistentAgent.Id);
    }

    private IChatClient GetOpenAIChatClient()
        => OpenAIClient
            .GetChatClient(TestConfiguration.OpenAI.ChatModelId)
            .AsIChatClient();

    private IChatClient GetAzureOpenAIChatClient()
        => ((TestConfiguration.AzureOpenAI.ApiKey is null)
            // Use Azure CLI credentials if API key is not provided.
            ? new AzureOpenAIClient(TestConfiguration.AzureOpenAI.Endpoint, new AzureCliCredential())
            : new AzureOpenAIClient(TestConfiguration.AzureOpenAI.Endpoint, new ApiKeyCredential(TestConfiguration.AzureOpenAI.ApiKey)))
                .GetChatClient(TestConfiguration.AzureOpenAI.DeploymentName)
                .AsIChatClient();

    private IChatClient GetOpenAIResponsesClient()
        => OpenAIClient
            .GetOpenAIResponseClient(TestConfiguration.OpenAI.ChatModelId)
            .AsIChatClient();
}
