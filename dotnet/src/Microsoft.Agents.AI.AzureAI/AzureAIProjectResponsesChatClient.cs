// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.AzureAI;

#pragma warning disable OPENAI001
internal sealed class AzureAIProjectResponsesChatClient : DelegatingChatClient
{
    private readonly ChatClientMetadata _metadata;
    private readonly AIProjectClient _aiProjectClient;

    internal AzureAIProjectResponsesChatClient(AIProjectClient aiProjectClient, string defaultModelId)
        : base(Throw.IfNull(aiProjectClient)
            .GetProjectOpenAIClient()
            .GetProjectResponsesClientForModel(Throw.IfNullOrWhitespace(defaultModelId))
            .AsIChatClient())
    {
        this._aiProjectClient = aiProjectClient;
        this._metadata = new ChatClientMetadata("microsoft.foundry", defaultModelId: defaultModelId);
    }

    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        return (serviceKey is null && serviceType == typeof(ChatClientMetadata))
            ? this._metadata
            : (serviceKey is null && serviceType == typeof(AIProjectClient))
            ? this._aiProjectClient
            : base.GetService(serviceType, serviceKey);
    }
}
#pragma warning restore OPENAI001
