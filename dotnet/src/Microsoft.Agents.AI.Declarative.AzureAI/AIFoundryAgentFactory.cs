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
public sealed class AIFoundryAgentFactory : AgentFactory
{
    /// <summary>
    /// Creates a new instance of the <see cref="AIFoundryAgentFactory"/> class.
    /// </summary>
    public AIFoundryAgentFactory()
    {
    }

    /// <summary>
    /// Creates a new instance of the <see cref="AIFoundryAgentFactory"/> class.
    /// </summary>
    public AIFoundryAgentFactory(PersistentAgentsClient agentClient)
    {
        Throw.IfNull(agentClient);

        this._agentClient = agentClient;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="AIFoundryAgentFactory"/> class.
    /// </summary>
    public AIFoundryAgentFactory(TokenCredential tokenCredential)
    {
        Throw.IfNull(tokenCredential);

        this._tokenCredential = tokenCredential;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="AIFoundryAgentFactory"/> class.
    /// </summary>
    public AIFoundryAgentFactory(IServiceProvider serviceProvider)
    {
        Throw.IfNull(serviceProvider);

        this._serviceProvider = serviceProvider;
    }

    /// <inheritdoc/>
    public override async Task<AIAgent?> TryCreateAsync(PromptAgent promptAgent, AgentCreationOptions? agentCreationOptions = null, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        var aiFoundryAgentOptions = agentCreationOptions as AIFoundryAgentCreationOptions;
        PersistentAgentsClient? agentClient = aiFoundryAgentOptions?.PersistentAgentsClient ?? this._agentClient;
        IServiceProvider? serviceProvider = agentCreationOptions?.ServiceProvider ?? this._serviceProvider;

        agentClient ??= serviceProvider?.GetService(typeof(PersistentAgentsClient)) as PersistentAgentsClient;

        if (agentClient is null)
        {
            var foundryConnection = promptAgent.Model?.Connection as FoundryConnection;
            if (foundryConnection is not null)
            {
                var endpoint = foundryConnection.Type; // TODO: Change to Endpoint when available in FoundryConnection
                if (string.IsNullOrEmpty(endpoint))
                {
                    throw new InvalidOperationException("The endpoint must be specified in the agent definition model connection to create an PersistentAgentsClient.");
                }
                TokenCredential? tokenCredential = this._tokenCredential ?? aiFoundryAgentOptions?.TokenCredential ?? serviceProvider?.GetService(typeof(TokenCredential)) as TokenCredential;
                if (tokenCredential is null)
                {
                    throw new InvalidOperationException("A TokenCredential must be registered in the service provider to create an PersistentAgentsClient.");
                }
                agentClient = new PersistentAgentsClient(endpoint, tokenCredential);
            }
            else
            {
                throw new InvalidOperationException("A PersistentAgentsClient must be registered in the service provider or a KeyConnection or OAuthConnection must be specified in the agent definition model connection to create an PersistentAgentsClient.");
            }
        }

        var modelId = promptAgent.Model?.Id;
        if (string.IsNullOrEmpty(modelId))
        {
            throw new InvalidOperationException("The model id must be specified in the agent definition model to create a foundry agent.");
        }

        var outputSchema = promptAgent.OutputSchema;
        OpenAIResponsesModel? model = promptAgent.Model as OpenAIResponsesModel;
        var modelOptions = model?.Options;

        return await agentClient.CreateAIAgentAsync(
            model: modelId,
            name: promptAgent.Name,
            instructions: promptAgent.Instructions?.ToTemplateString(),
            tools: promptAgent.GetToolDefinitions(aiFoundryAgentOptions?.Tools),
            toolResources: promptAgent.GetToolResources(),
            temperature: (float?)modelOptions?.Temperature?.LiteralValue,
            topP: (float?)modelOptions?.TopP?.LiteralValue,
            responseFormat: outputSchema.AsBinaryData(),
            metadata: promptAgent.Metadata?.ToDictionary(),
            cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    #region
    private readonly PersistentAgentsClient? _agentClient;
    private readonly TokenCredential? _tokenCredential;
    private readonly IServiceProvider? _serviceProvider;
    #endregion
}
