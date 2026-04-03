// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;
using OpenAI.Responses;

namespace Azure.AI.Extensions.OpenAI;

/// <summary>
/// Provides extension methods for <see cref="ProjectResponsesClient"/>
/// to simplify the creation of AI agents that work with Azure AI services.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public static class ProjectResponsesClientExtensions
{
    /// <summary>
    /// Gets an <see cref="IChatClient"/> for use with this <see cref="ProjectResponsesClient"/> that does not store responses for later retrieval.
    /// </summary>
    /// <remarks>
    /// This corresponds to setting the "store" property in the JSON representation to false.
    /// </remarks>
    /// <param name="responseClient">The client.</param>
    /// <param name="deploymentName">Optional deployment name (model) to use for requests.</param>
    /// <param name="includeReasoningEncryptedContent">
    /// Includes an encrypted version of reasoning tokens in reasoning item outputs.
    /// This enables reasoning items to be used in multi-turn conversations when using the Responses API statelessly
    /// (like when the store parameter is set to false, or when an organization is enrolled in the zero data retention program).
    /// Defaults to <see langword="true"/>.
    /// </param>
    /// <returns>An <see cref="IChatClient"/> that can be used to converse via the <see cref="ProjectResponsesClient"/> that does not store responses for later retrieval.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="responseClient"/> is <see langword="null"/>.</exception>
    [Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
    public static IChatClient AsIChatClientWithStoredOutputDisabled(this ProjectResponsesClient responseClient, string? deploymentName = null, bool includeReasoningEncryptedContent = true)
    {
        return Throw.IfNull(responseClient)
            .AsIChatClient(deploymentName)
            .AsBuilder()
            .ConfigureOptions(x =>
            {
                var previousFactory = x.RawRepresentationFactory;
                x.RawRepresentationFactory = state =>
                {
                    var responseOptions = previousFactory?.Invoke(state) as CreateResponseOptions ?? new CreateResponseOptions();

                    responseOptions.StoredOutputEnabled = false;

                    if (includeReasoningEncryptedContent &&
                        !responseOptions.IncludedProperties.Contains(IncludedResponseProperty.ReasoningEncryptedContent))
                    {
                        responseOptions.IncludedProperties.Add(IncludedResponseProperty.ReasoningEncryptedContent);
                    }

                    return responseOptions;
                };
            })
            .Build();
    }
}
