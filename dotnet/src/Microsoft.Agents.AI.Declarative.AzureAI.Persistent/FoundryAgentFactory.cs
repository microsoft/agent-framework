// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents;
using Azure.AI.Agents.Persistent;
using Azure.Core;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.Configuration;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="AgentFactory"/> which creates instances of <see cref="AIAgent"/> using a <see cref="AgentClient"/>.
/// </summary>
public sealed class FoundryAgentFactory : AgentFactory
{
    private readonly AgentClient? _agentClient;
    private readonly TokenCredential? _tokenCredential;

    /// <summary>
    /// Creates a new instance of the <see cref="FoundryAgentFactory"/> class with an associated <see cref="AgentClient"/>.
    /// </summary>
    /// <param name="agentClient">The <see cref="AgentClient"/> instance to use for creating agents.</param>
    /// <param name="configuration">The <see cref="IConfiguration"/> instance to use for configuration.</param>
    public FoundryAgentFactory(AgentClient agentClient, IConfiguration? configuration = null) : base(configuration)
    {
        Throw.IfNull(agentClient);

        this._agentClient = agentClient;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="FoundryAgentFactory"/> class with an associated <see cref="TokenCredential"/>.
    /// </summary>
    /// <param name="tokenCredential">The <see cref="TokenCredential"/> to use for authenticating requests.</param>
    /// <param name="configuration">The <see cref="IConfiguration"/> instance to use for configuration.</param>
    public FoundryAgentFactory(TokenCredential tokenCredential, IConfiguration? configuration = null) : base(configuration)
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
    }

    private AgentClient CreateAgentClient(GptComponentMetadata promptAgent)
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

            return new AgentClient(new Uri(endpoint), this._tokenCredential);
        }

        throw new InvalidOperationException("An AgentClient must be registered in the service provider or a RemoteConnection must be specified in the agent definition model connection to create an AgentClient.");
    }
}
