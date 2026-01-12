// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.Core;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.Configuration;
using Microsoft.PowerFx;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="PromptAgentFactory"/> which creates instances of <see cref="AIAgent"/> using a <see cref="PersistentAgentsClient"/>.
/// </summary>
public sealed class FoundryAgentFactory : PromptAgentFactory
{
    private readonly PersistentAgentsClient? _agentClient;
    private readonly TokenCredential? _tokenCredential;

    /// <summary>
    /// Creates a new instance of the <see cref="FoundryAgentFactory"/> class with an associated <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="agentClient">The <see cref="PersistentAgentsClient"/> instance to use for creating agents.</param>
    /// <param name="engine">Optional <see cref="RecalcEngine"/>, if none is provided a default instance will be created.</param>
    /// <param name="configuration">The <see cref="IConfiguration"/> instance to use for configuration.</param>
    public FoundryAgentFactory(PersistentAgentsClient agentClient, RecalcEngine? engine = null, IConfiguration? configuration = null) : base(engine, configuration)
    {
        Throw.IfNull(agentClient);

        this._agentClient = agentClient;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="FoundryAgentFactory"/> class with an associated <see cref="TokenCredential"/>.
    /// </summary>
    /// <param name="tokenCredential">The <see cref="TokenCredential"/> to use for authenticating requests.</param>
    /// <param name="engine">Optional <see cref="RecalcEngine"/>, if none is provided a default instance will be created.</param>
    /// <param name="configuration">The <see cref="IConfiguration"/> instance to use for configuration.</param>
    public FoundryAgentFactory(TokenCredential tokenCredential, RecalcEngine? engine = null, IConfiguration? configuration = null) : base(engine, configuration)
    {
        Throw.IfNull(tokenCredential);

        this._tokenCredential = tokenCredential;
    }

    /// <inheritdoc/>
    public override async Task<AIAgent?> TryCreateAsync(GptComponentMetadata promptAgent, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        var agentClient = this._agentClient ?? this.CreateAgentClient(promptAgent);

        var modelId = promptAgent.Model?.ModelNameHint;
        if (string.IsNullOrEmpty(modelId))
        {
            throw new InvalidOperationException("The model id must be specified in the agent definition model to create a foundry agent.");
        }

        var modelOptions = promptAgent.Model?.Options;

        /*
        var promptAgentDefinition = new PromptAgentDefinition(model: modelId)
        {
            Instructions = promptAgent.Instructions?.ToTemplateString(),
            Temperature = (float?)modelOptions?.Temperature?.LiteralValue,
            TopP = (float?)modelOptions?.TopP?.LiteralValue,
        };

        foreach (var tool in promptAgent.GetResponseTools())
        {
            promptAgentDefinition.Tools.Add(tool);
        }

        var agentVersionCreationOptions = new AgentVersionCreationOptions(promptAgentDefinition);

        var metadata = promptAgent.Metadata?.ToDictionary();
        if (metadata is not null)
        {
            foreach (var kvp in metadata)
            {
                agentVersionCreationOptions.Metadata.Add(kvp.Key, kvp.Value);
            }
        }

        var agentVersion = await agentClient.CreateAgentVersionAsync(agentName: promptAgent.Name, options: agentVersionCreationOptions, cancellationToken: cancellationToken).ConfigureAwait(false);

        return agentClient.GetAIAgent(agentVersion, cancellationToken: cancellationToken);
        */

        var createPersistentAgentResponse = agentClient.Administration.CreateAgent(
            model: modelId,
            name: promptAgent.Name,
            instructions: promptAgent.Instructions?.ToTemplateString(),
            tools: tools,
            toolResources: toolResources,
            temperature: (float?)modelOptions?.Temperature?.LiteralValue,
            topP: (float?)modelOptions?.TopP?.LiteralValue,
            responseFormat: responseFormat,
            metadata: promptAgent.Metadata?.ToDictionary(),
            cancellationToken: cancellationToken);

        // Get a local proxy for the agent to work with.
        return agentClient.GetAIAgent(createPersistentAgentResponse.Value.Id, clientFactory: null, services: null, cancellationToken: cancellationToken);
    }

    private PersistentAgentsClient CreateAgentClient(GptComponentMetadata promptAgent)
    {
        var externalModel = promptAgent.Model as CurrentModels;
        var connection = externalModel?.Connection as RemoteConnection;
        if (connection is not null)
        {
            var endpoint = connection.Endpoint?.Eval(this.Engine);
            if (string.IsNullOrEmpty(endpoint))
            {
                throw new InvalidOperationException("The endpoint must be specified in the agent definition model connection to create an AgentClient.");
            }

            if (this._tokenCredential is null)
            {
                throw new InvalidOperationException("A TokenCredential must be registered in the service provider to create an AgentClient.");
            }

            return new PersistentAgentsClient(endpoint, this._tokenCredential);
        }

        throw new InvalidOperationException("A PersistentAgentsClient must be registered in the service provider or a RemoteConnection must be specified in the agent definition model connection to create a PersistentAgentsClient.");
    }
}
