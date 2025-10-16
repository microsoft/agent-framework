// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.Core;
using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="AgentFactory"/> which creates instances of <see cref="ChatClientAgent"/> using a <see cref="PersistentAgentsClient"/>.
/// </summary>
public sealed class AzureFoundryAgentFactory : AgentFactory
{
    /// <inheritdoc/>
    public override async Task<AIAgent?> TryCreateAsync(PromptAgent promptAgent, AgentCreationOptions agentCreationOptions, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        if (agentCreationOptions.ServiceProvider?.GetService(typeof(PersistentAgentsClient)) is not PersistentAgentsClient persistentAgentsClient)
        {
            var foundryConnection = promptAgent.Model?.Connection as FoundryConnection;
            if (foundryConnection is not null)
            {
                var endpoint = foundryConnection.Type; // TODO: Change to Endpoint when available in FoundryConnection
                if (string.IsNullOrEmpty(endpoint))
                {
                    throw new InvalidOperationException("The endpoint must be specified in the agent definition model connection to create an PersistentAgentsClient.");
                }
                if (agentCreationOptions.ServiceProvider?.GetService(typeof(TokenCredential)) is not TokenCredential tokenCredential)
                {
                    throw new InvalidOperationException("A TokenCredential must be registered in the service provider to create an PersistentAgentsClient.");
                }
                persistentAgentsClient = new PersistentAgentsClient(endpoint, tokenCredential);
            }
            else
            {
                throw new InvalidOperationException("A PersistentAgentsClient must be registered in the service provider or a KeyConnection or OAuthConnection must be specified in the agent definition model connection to create an PersistentAgentsClient.");
            }
        }

        var modelId = agentCreationOptions?.Model ?? promptAgent.Model?.Id;
        if (string.IsNullOrEmpty(modelId))
        {
            throw new InvalidOperationException("The model id must be specified in the agent definition model to create a foundry agent.");
        }

        var outputSchema = promptAgent.OutputSchema;
        OpenAIResponsesModel? model = promptAgent.Model as OpenAIResponsesModel;
        var modelOptions = model?.Options;

        return await persistentAgentsClient.CreateAIAgentAsync(
            model: modelId,
            name: promptAgent.Name,
            instructions: promptAgent.Instructions?.ToTemplateString(),
            tools: promptAgent.GetToolDefinitions(agentCreationOptions?.Tools),
            toolResources: promptAgent.GetToolResources(),
            temperature: (float?)modelOptions?.Temperature?.LiteralValue,
            topP: (float?)modelOptions?.TopP?.LiteralValue,
            responseFormat: outputSchema.AsBinaryData(),
            metadata: promptAgent.Metadata?.ToDictionary(),
            cancellationToken: cancellationToken).ConfigureAwait(false);
    }
}
