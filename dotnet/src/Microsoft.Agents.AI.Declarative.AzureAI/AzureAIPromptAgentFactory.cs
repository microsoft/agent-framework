// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Azure.Core;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.Configuration;
using Microsoft.PowerFx;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="PromptAgentFactory"/> which creates instances of <see cref="AIAgent"/> using a <see cref="AIProjectClient"/>.
/// </summary>
public sealed class AzureAIPromptAgentFactory : PromptAgentFactory
{
    private readonly AIProjectClient? _projectClient;
    private readonly TokenCredential? _tokenCredential;

    /// <summary>
    /// Creates a new instance of the <see cref="AzureAIPromptAgentFactory"/> class with an associated <see cref="AIProjectClient"/>.
    /// </summary>
    /// <param name="projectClient">The <see cref="AIProjectClient"/> instance to use for creating agents.</param>
    /// <param name="engine">Optional <see cref="RecalcEngine"/>, if none is provided a default instance will be created.</param>
    /// <param name="configuration">The <see cref="IConfiguration"/> instance to use for configuration.</param>
    public AzureAIPromptAgentFactory(AIProjectClient projectClient, RecalcEngine? engine = null, IConfiguration? configuration = null) : base(engine, configuration)
    {
        Throw.IfNull(projectClient);

        this._projectClient = projectClient;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="AzureAIPromptAgentFactory"/> class with an associated <see cref="TokenCredential"/>.
    /// </summary>
    /// <param name="tokenCredential">The <see cref="TokenCredential"/> to use for authenticating requests.</param>
    /// <param name="engine">Optional <see cref="RecalcEngine"/>, if none is provided a default instance will be created.</param>
    /// <param name="configuration">The <see cref="IConfiguration"/> instance to use for configuration.</param>
    public AzureAIPromptAgentFactory(TokenCredential tokenCredential, RecalcEngine? engine = null, IConfiguration? configuration = null) : base(engine, configuration)
    {
        Throw.IfNull(tokenCredential);

        this._tokenCredential = tokenCredential;
    }

    /// <inheritdoc/>
    public override async Task<AIAgent?> TryCreateAsync(GptComponentMetadata promptAgent, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);
        Throw.IfNullOrEmpty(promptAgent.Name);

        var projectClient = this._projectClient ?? this.CreateAIProjectClient(promptAgent);

        var modelId = promptAgent.Model?.ModelNameHint;
        if (string.IsNullOrEmpty(modelId))
        {
            throw new InvalidOperationException("The model id must be specified in the agent definition model to create a foundry agent.");
        }

        return await projectClient.CreateAIAgentAsync(
            name: promptAgent.Name,
            model: modelId,
            instructions: promptAgent.Instructions?.ToTemplateString() ?? string.Empty,
            description: promptAgent.Description,
            tools: promptAgent.GetAITools(),
            cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    private AIProjectClient CreateAIProjectClient(GptComponentMetadata promptAgent)
    {
        var externalModel = promptAgent.Model as CurrentModels;
        var connection = externalModel?.Connection as RemoteConnection;
        if (connection is not null)
        {
            var endpoint = connection.Endpoint?.Eval(this.Engine);
            if (string.IsNullOrEmpty(endpoint))
            {
                throw new InvalidOperationException("The endpoint must be specified in the agent definition model connection to create an AIProjectClient.");
            }
            if (this._tokenCredential is null)
            {
                throw new InvalidOperationException("A TokenCredential must be registered in the service provider to create an AIProjectClient.");
            }
            return new AIProjectClient(new Uri(endpoint), this._tokenCredential);
        }

        throw new InvalidOperationException("A AIProjectClient must be registered in the service provider or a FoundryConnection must be specified in the agent definition model connection to create an AIProjectClient.");
    }
}
