// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Provides configuration options for <see cref="TypeSafeDecisionClient"/>.
/// </summary>
/// <remarks>
/// This is a class rather than a record on purpose: a record's generated <c>ToString()</c> would print any secret that
/// lives on it. The API key is passed to the client constructor and is never stored on the options.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class TypeSafeDecisionClientOptions
{
    /// <summary>TypeSafe's System One endpoint (<c>POST</c>), per the TypeSafe API reference.</summary>
    public const string DefaultEndpoint = "https://api.typesafe.ai/v1/systemone";

    /// <summary>
    /// OpenRouter's relay of the same protocol. When targeting it, use OpenRouter's model identifiers (for example
    /// <c>typesafe/jev-1.13</c>) and an OpenRouter API key.
    /// </summary>
    public const string OpenRouterEndpoint = "https://openrouter.ai/api/v1/systemone";

    /// <summary>
    /// TypeSafe's flagship alias. It moves between releases; the <see cref="DecisionResponse.ModelId"/> a response carries
    /// is the resolved build. Pin a versioned identifier such as <c>jev-1.13.0</c> for reproducible runs.
    /// </summary>
    public const string DefaultModelId = "jev-latest";

    /// <summary>Gets or sets the full request URL. Defaults to <see cref="DefaultEndpoint"/>.</summary>
    public Uri Endpoint { get; set; } = new(DefaultEndpoint);

    /// <summary>Gets or sets the model identifier sent when a request does not override it. Defaults to <see cref="DefaultModelId"/>.</summary>
    public string ModelId { get; set; } = DefaultModelId;

    /// <summary>Gets or sets the request timeout applied when the client creates its own <see cref="System.Net.Http.HttpClient"/>. Defaults to 60 seconds.</summary>
    public TimeSpan Timeout { get; set; } = TimeSpan.FromSeconds(60);
}
