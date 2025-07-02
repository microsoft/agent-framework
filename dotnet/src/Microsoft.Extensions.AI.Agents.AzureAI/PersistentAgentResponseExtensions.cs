// Copyright (c) Microsoft. All rights reserved.

using Azure;
using Azure.AI.Agents.Persistent;
using Azure.Core;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Extensions.AI.AzureAIAgentsPersistent;

/// <summary>
/// Extension methods for <see cref="Response{PersistentAgent}"/>.
/// </summary>
public static class PersistentAgentResponseExtensions
{
    /// <summary>
    /// Converts a <see cref="Response{PersistentAgent}"/> to a <see cref="ChatClientAgent"/>.
    /// </summary>
    /// <param name="response">The <see cref="Response{PersistentAgent}"/> to convert.</param>
    /// <param name="endpoint"> The Azure AI Foundry project endpoint, in the form `https://&lt;aiservices-id&gt;.services.ai.azure.com/api/projects/&lt;project-name&gt;`</param>
    /// <param name="credential"> A credential used to authenticate to an Azure Service. </param>
    /// <returns>A <see cref="ChatClientAgent"/> for the created persistent agent.</returns>
    public static ChatClientAgent AsChatClientAgent(this Response<PersistentAgent> response, string endpoint, TokenCredential credential)
    {
        var persistentAgent = response.Value;
        var persistentAgentsClient = new PersistentAgentsClient(endpoint, credential);
#pragma warning disable CA2000 // Dispose objects before losing scope
        var chatClient = persistentAgentsClient.AsIChatClient(persistentAgent.Id);
#pragma warning restore CA2000 // Dispose objects before losing scope
        return new ChatClientAgent(chatClient, new ChatClientAgentOptions { Id = persistentAgent.Id, Name = persistentAgent.Name, Instructions = persistentAgent.Instructions });
    }
}
