// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.FoundryLocal;

/// <summary>
/// Configuration options for creating a <see cref="FoundryLocalChatClient"/>.
/// </summary>
/// <remarks>
/// <para>
/// These options control how the Foundry Local manager is initialized, whether models are
/// automatically downloaded and loaded, and whether the OpenAI-compatible HTTP endpoint is started.
/// </para>
/// <para>
/// The <see cref="Model"/> property is required and specifies the model alias to use (e.g., "phi-4-mini").
/// If not set explicitly, it can be resolved from the <c>FOUNDRY_LOCAL_MODEL</c> environment variable.
/// </para>
/// </remarks>
public sealed class FoundryLocalClientOptions
{
    /// <summary>
    /// Gets or sets the model alias or identifier to use (e.g., "phi-4-mini").
    /// </summary>
    /// <remarks>
    /// If not set, the value will be resolved from the <c>FOUNDRY_LOCAL_MODEL</c> environment variable.
    /// This property must be set (either directly or via the environment variable) before creating a
    /// <see cref="FoundryLocalChatClient"/>.
    /// </remarks>
    public string? Model { get; set; }

    /// <summary>
    /// Gets or sets the application name used when initializing the <see cref="Microsoft.AI.Foundry.Local.FoundryLocalManager"/>.
    /// </summary>
    /// <value>The default value is <c>"AgentFramework"</c>.</value>
    public string AppName { get; set; } = "AgentFramework";

    /// <summary>
    /// Gets or sets a value indicating whether to automatically create and initialize the
    /// <see cref="Microsoft.AI.Foundry.Local.FoundryLocalManager"/> if it has not already been initialized.
    /// </summary>
    /// <value>The default value is <see langword="true"/>.</value>
    public bool Bootstrap { get; set; } = true;

    /// <summary>
    /// Gets or sets a value indicating whether to automatically download and load the specified model
    /// during initialization.
    /// </summary>
    /// <remarks>
    /// When set to <see langword="true"/>, the model will be downloaded to the local cache (if not already cached)
    /// and loaded into the inference service. When set to <see langword="false"/>, the model will be loaded on
    /// the first inference request, which may cause a significant delay.
    /// </remarks>
    /// <value>The default value is <see langword="true"/>.</value>
    public bool PrepareModel { get; set; } = true;

    /// <summary>
    /// Gets or sets a value indicating whether to start the OpenAI-compatible HTTP web service endpoint
    /// if it is not already running.
    /// </summary>
    /// <value>The default value is <see langword="true"/>.</value>
    public bool StartWebService { get; set; } = true;

    /// <summary>
    /// Gets or sets an optional custom binding URL for the web service endpoint.
    /// </summary>
    /// <remarks>
    /// When set, this URL will be used to configure the web service binding via
    /// <see cref="Microsoft.AI.Foundry.Local.Configuration.Web"/>.
    /// When <see langword="null"/>, the default URL (typically <c>http://localhost:5272</c>) is used.
    /// </remarks>
    public Uri? WebServiceUrl { get; set; }

    /// <summary>
    /// Resolves the model name from the <see cref="Model"/> property or the <c>FOUNDRY_LOCAL_MODEL</c> environment variable.
    /// </summary>
    /// <returns>The resolved model name.</returns>
    /// <exception cref="InvalidOperationException">
    /// Thrown when neither the <see cref="Model"/> property nor the <c>FOUNDRY_LOCAL_MODEL</c> environment variable is set.
    /// </exception>
    internal string ResolveModel()
    {
        var model = Model ?? Environment.GetEnvironmentVariable("FOUNDRY_LOCAL_MODEL");

        if (string.IsNullOrWhiteSpace(model))
        {
            throw new InvalidOperationException(
                "A model must be specified. Set the 'Model' property on FoundryLocalClientOptions " +
                "or set the 'FOUNDRY_LOCAL_MODEL' environment variable.");
        }

        return model;
    }
}
