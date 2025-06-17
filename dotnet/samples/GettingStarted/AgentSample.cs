// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Samples;
using OpenAI;

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
    }

    protected IChatClient GetChatClient(ChatClientProviders provider)
    {
        return provider switch
        {
            ChatClientProviders.OpenAI => GetOpenAIChatClient(),
            ChatClientProviders.AzureOpenAI => GetAzureOpenAIChatClient(),
            _ => throw new NotSupportedException($"Provider {provider} is not supported.")
        };
    }

    private IChatClient GetOpenAIChatClient()
        => new OpenAIClient(TestConfiguration.OpenAI.ApiKey)
            .GetChatClient(TestConfiguration.OpenAI.ChatModelId)
            .AsIChatClient();

    private IChatClient GetAzureOpenAIChatClient()
    {
        AzureOpenAIClient client;

        if (TestConfiguration.AzureOpenAI.ApiKey is null)
        {
            client = new AzureOpenAIClient(TestConfiguration.AzureOpenAI.Endpoint,
                new AzureCliCredential());
        }
        else
        {
            client = new AzureOpenAIClient(TestConfiguration.AzureOpenAI.Endpoint,
                new ApiKeyCredential(TestConfiguration.AzureOpenAI.ApiKey));
        }

        return client.GetChatClient(TestConfiguration.AzureOpenAI.DeploymentName)
            .AsIChatClient();
    }
}
