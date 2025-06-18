// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Samples;
using OpenAI;
using OpenAI.Responses;

namespace GettingStarted;

public class AgentSample(ITestOutputHelper output) : BaseSample(output)
{
    /// <summary>
    /// Represents the available providers for <see cref="IChatClient"/> instances.
    /// </summary>
    public enum ChatClientProviders
    {
        OpenAI,
        AzureOpenAI,
        OpenAIResponses
    }

    public enum ThreadStoreType
    {
        InMemoryMessage,
        ConversationId
    }

    protected IChatClient GetChatClient(ChatClientProviders provider)
    {
        return provider switch
        {
            ChatClientProviders.OpenAI => GetOpenAIChatClient(),
            ChatClientProviders.AzureOpenAI => GetAzureOpenAIChatClient(),
            ChatClientProviders.OpenAIResponses => GetOpenAIResponsesClient(),
            _ => throw new NotSupportedException($"Provider {provider} is not supported.")
        };
    }

    protected ChatOptions? GetChatOptions(ThreadStoreType? provider)
    {
        // Create chat options based on the provider.
        return provider switch
        {
            ThreadStoreType.InMemoryMessage => new ChatOptions() { RawRepresentationFactory = static (_) => new ResponseCreationOptions() { StoredOutputEnabled = false } },
            ThreadStoreType.ConversationId => new ChatOptions() { RawRepresentationFactory = static (_) => new ResponseCreationOptions() { StoredOutputEnabled = true } },
            _ => null
        };
    }

    private IChatClient GetOpenAIChatClient()
        => new OpenAIClient(TestConfiguration.OpenAI.ApiKey)
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
    {
        // Create a client to get responses from OpenAI.
        return new OpenAIClient(TestConfiguration.OpenAI.ApiKey)
            .GetOpenAIResponseClient(TestConfiguration.OpenAI.ChatModelId)
            .AsIChatClient();
    }
}
