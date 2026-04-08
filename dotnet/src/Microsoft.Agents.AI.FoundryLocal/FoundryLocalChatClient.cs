// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AI.Foundry.Local;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;
using OpenAI;

namespace Microsoft.Agents.AI.FoundryLocal;

/// <summary>
/// A <see cref="DelegatingChatClient"/> that uses AI Foundry Local for on-device model inference.
/// </summary>
/// <remarks>
/// <para>
/// This client manages the lifecycle of a local AI model through the Foundry Local SDK,
/// including model discovery, download, loading, and serving via an OpenAI-compatible HTTP endpoint.
/// </para>
/// <para>
/// Because initialization requires asynchronous operations (model download, loading, and web service startup),
/// instances must be created using the <see cref="CreateAsync"/> static factory method rather than
/// a constructor.
/// </para>
/// <para>
/// Internally, this client creates an <see cref="OpenAIClient"/> pointed at the local Foundry endpoint
/// (typically <c>http://localhost:5272</c>) and wraps it as an <see cref="IChatClient"/>.
/// This avoids conflicts with the Foundry Local SDK's internal use of a different OpenAI client library.
/// </para>
/// </remarks>
#pragma warning disable OPENAI001
public sealed class FoundryLocalChatClient : DelegatingChatClient
{
    private readonly ChatClientMetadata _metadata;

    /// <summary>
    /// Gets the <see cref="FoundryLocalManager"/> instance managing the local model service.
    /// </summary>
    public FoundryLocalManager Manager { get; }

    /// <summary>
    /// Gets the resolved model identifier being used for inference.
    /// </summary>
    public string ModelId { get; }

    private FoundryLocalChatClient(IChatClient innerClient, FoundryLocalManager manager, string modelId)
        : base(innerClient)
    {
        Manager = manager;
        ModelId = modelId;
        _metadata = new ChatClientMetadata("microsoft.foundry.local", defaultModelId: modelId);
    }

    /// <summary>
    /// Creates a new <see cref="FoundryLocalChatClient"/> instance with the specified options.
    /// </summary>
    /// <param name="options">The configuration options for the Foundry Local client. Cannot be <see langword="null"/>.</param>
    /// <param name="logger">An optional logger for diagnostic output during initialization.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the initialization.</param>
    /// <returns>A task that represents the asynchronous creation operation, containing the initialized <see cref="FoundryLocalChatClient"/>.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">
    /// Thrown when the model cannot be resolved from the options or environment, when the specified model is not found
    /// in the Foundry Local catalog, or when the web service endpoint is not available after startup.
    /// </exception>
    /// <remarks>
    /// <para>
    /// This method performs the following steps based on the provided <paramref name="options"/>:
    /// </para>
    /// <list type="number">
    /// <item><description>Resolves the model name from options or the <c>FOUNDRY_LOCAL_MODEL</c> environment variable.</description></item>
    /// <item><description>Bootstraps the <see cref="FoundryLocalManager"/> if not already initialized (when <see cref="FoundryLocalClientOptions.Bootstrap"/> is <see langword="true"/>).</description></item>
    /// <item><description>Resolves the model from the catalog using the model alias.</description></item>
    /// <item><description>Downloads and loads the model if <see cref="FoundryLocalClientOptions.PrepareModel"/> is <see langword="true"/>.</description></item>
    /// <item><description>Starts the web service endpoint if <see cref="FoundryLocalClientOptions.StartWebService"/> is <see langword="true"/>.</description></item>
    /// <item><description>Creates an <see cref="OpenAIClient"/> pointed at the local endpoint and wraps it as an <see cref="IChatClient"/>.</description></item>
    /// </list>
    /// </remarks>
    public static async Task<FoundryLocalChatClient> CreateAsync(
        FoundryLocalClientOptions options,
        ILogger? logger = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(options);

        logger ??= NullLogger.Instance;

        // 1. Resolve model name
        var modelName = options.ResolveModel();

        // 2. Bootstrap FoundryLocalManager if needed
        if (options.Bootstrap && !FoundryLocalManager.IsInitialized)
        {
            var webServiceUrl = options.WebServiceUrl?.ToString() ?? "http://localhost:5272";

            var config = new Configuration
            {
                AppName = options.AppName,
                Web = new Configuration.WebService { Urls = webServiceUrl },
            };

            await FoundryLocalManager.CreateAsync(config, logger, cancellationToken).ConfigureAwait(false);
        }

        if (!FoundryLocalManager.IsInitialized)
        {
            throw new InvalidOperationException(
                "FoundryLocalManager is not initialized. Enable Bootstrap to initialize it automatically, " +
                "or initialize FoundryLocalManager manually before creating a FoundryLocalChatClient.");
        }

        var manager = FoundryLocalManager.Instance;

        // 3. Get catalog and resolve model
        var catalog = await manager.GetCatalogAsync(cancellationToken).ConfigureAwait(false);
        var model = await catalog.GetModelAsync(modelName, cancellationToken).ConfigureAwait(false);

        if (model is null)
        {
            throw new InvalidOperationException(
                $"Model with alias '{modelName}' was not found in the Foundry Local catalog. " +
                "Use FoundryLocalManager to list available models.");
        }

        var resolvedModelId = model.Id;

        // 4. Download and load model if requested
        if (options.PrepareModel)
        {
            if (!await model.IsCachedAsync(cancellationToken).ConfigureAwait(false))
            {
                await model.DownloadAsync().ConfigureAwait(false);
            }

            if (!await model.IsLoadedAsync(cancellationToken).ConfigureAwait(false))
            {
                await model.LoadAsync(cancellationToken).ConfigureAwait(false);
            }
        }

        // 5. Start web service if needed
        if (options.StartWebService && manager.Urls is null)
        {
            await manager.StartWebServiceAsync(cancellationToken).ConfigureAwait(false);
        }

        var urls = manager.Urls;
        if (urls is null || urls.Length == 0)
        {
            throw new InvalidOperationException(
                "The Foundry Local web service is not running and no endpoint URLs are available. " +
                "Ensure StartWebService is enabled or start the service manually.");
        }

        // 6. Create OpenAI client pointed at the local endpoint
        // Foundry Local serves OpenAI-compatible API at /v1/ (e.g., /v1/chat/completions)
        var endpointUrl = urls[0].TrimEnd('/') + "/v1";
        var openAIClient = new OpenAIClient(
            new ApiKeyCredential("foundry-local"),
            new OpenAIClientOptions { Endpoint = new Uri(endpointUrl) });

        // 7. Get ChatClient and wrap as IChatClient
        var chatClient = openAIClient.GetChatClient(resolvedModelId);
        var innerChatClient = chatClient.AsIChatClient();

        return new FoundryLocalChatClient(innerChatClient, manager, resolvedModelId);
    }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        return (serviceKey is null && serviceType == typeof(ChatClientMetadata))
            ? _metadata
            : (serviceKey is null && serviceType == typeof(FoundryLocalManager))
            ? Manager
            : base.GetService(serviceType, serviceKey);
    }
}
#pragma warning restore OPENAI001
