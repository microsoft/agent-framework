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
/// Provides an <see cref="AgentFactory"/> which creates instances of <see cref="AIAgent"/> using a <see cref="PersistentAgentsClient"/>.
/// </summary>
public sealed class FoundryPersistentAgentFactory : AgentFactory
{
    /// <summary>
    /// Creates a new instance of the <see cref="FoundryPersistentAgentFactory"/> class.
    /// </summary>
    public FoundryPersistentAgentFactory(PersistentAgentsClient agentClient)
    {
        Throw.IfNull(agentClient);

        this._agentClient = agentClient;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="FoundryPersistentAgentFactory"/> class.
    /// </summary>
    public FoundryPersistentAgentFactory(TokenCredential tokenCredential)
    {
        Throw.IfNull(tokenCredential);

        this._tokenCredential = tokenCredential;
    }

    /// <inheritdoc/>
    public override async Task<AIAgent?> TryCreateAsync(GptComponentMetadata promptAgent, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        var agentClient = this._agentClient ?? this.CreatePersistentAgentClient(promptAgent);

        var modelId = promptAgent.Model?.ModelNameHint;
        if (string.IsNullOrEmpty(modelId))
        {
            throw new InvalidOperationException("The model id must be specified in the agent definition model to create a foundry agent.");
        }

        var outputSchema = promptAgent.OutputType;
        var modelOptions = promptAgent.Model?.Options;

        return await agentClient.CreateAIAgentAsync(
            model: modelId,
            name: promptAgent.Name,
            instructions: promptAgent.Instructions?.ToTemplateString(),
            tools: promptAgent.GetToolDefinitions(),
            toolResources: promptAgent.GetToolResources(),
            temperature: (float?)modelOptions?.Temperature?.LiteralValue,
            topP: (float?)modelOptions?.TopP?.LiteralValue,
            // responseFormat: outputSchema.AsBinaryData(), TODO: Fix converting RecordDataType to BinaryData
            metadata: promptAgent.Metadata?.ToDictionary(),
            cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    #region
    private readonly PersistentAgentsClient? _agentClient;
    private readonly TokenCredential? _tokenCredential;

    private PersistentAgentsClient CreatePersistentAgentClient(GptComponentMetadata promptAgent)
    {
        var connection = promptAgent.Model?.Connection;
        if (connection is not null/* && connection is ApiKeyConnection keyConnection*/)
        {
            var endpoint = connection.ExtensionData?.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("endpoint"))?.Value; // keyConnection.Endpoint?.LiteralValue;
            if (string.IsNullOrEmpty(endpoint))
            {
                throw new InvalidOperationException("The endpoint must be specified in the agent definition model connection to create an PersistentAgentsClient.");
            }
            if (this._tokenCredential is null)
            {
                throw new InvalidOperationException("A TokenCredential must be registered in the service provider to create an PersistentAgentsClient.");
            }
            return new PersistentAgentsClient(endpoint, this._tokenCredential);
        }

        throw new InvalidOperationException("A PersistentAgentsClient must be registered in the service provider or a FoundryConnection must be specified in the agent definition model connection to create an PersistentAgentsClient.");
    }

    #endregion
}
