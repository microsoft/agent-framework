// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using Microsoft.Extensions.AI;
using OpenAI;
using IChatClient = Microsoft.Extensions.AI.IChatClient;

namespace Common;

public static class DefaultExtensions
{
    public static ModelSettings GetModel(this IConfiguration configuration)
    {
        var section = configuration.GetSection(ModelSettings.SectionName).Get<ModelSettings>();
        return section ?? throw new InvalidOperationException("缺少配置节 Llm");
    }

    public static OpenAI.Chat.ChatClient CreateChatClient(this ModelSettings settings)
    {
        var options = new OpenAIClientOptions
        {
            Endpoint = new Uri(settings.Endpoint!.TrimEnd('/') + "/")
        };
        var client = new OpenAIClient(new ApiKeyCredential(settings.ApiKey), options);
        return client.GetChatClient(settings.Model);
    }

    public static IChatClient CreateAIChatClient(this ModelSettings settings)
    {
        var options = new OpenAIClientOptions
        {
            Endpoint = new Uri(settings.Endpoint!.TrimEnd('/') + "/")
        };
        var client = new OpenAIClient(new ApiKeyCredential(settings.ApiKey), options);
        return client.GetChatClient(settings.Model).AsIChatClient();
    }
}
