// Copyright (c) Microsoft. All rights reserved.

using System;
using Azure.Storage.Blobs;
using Microsoft.Agents.AI.Hosting.AzureStorage.Blob;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides extension methods for configuring <see cref="AIAgent"/>.
/// </summary>
public static partial class HostedAgentBuilderExtensions
{
    /// <summary>
    /// Configures the host agent builder to use an Azure Blob thread store for agent thread management.
    /// </summary>
    /// <param name="builder">The host agent builder to configure with the Azure blob thread store.</param>
    /// <param name="containerClient">The blob container client to use for storage operations.</param>
    /// <param name="options">Optional configuration options for the blob thread store.</param>
    /// <returns>The same <paramref name="builder"/> instance, configured to use Azure blob thread store.</returns>
    public static IHostedAgentBuilder WithAzureBlobThreadStore(this IHostedAgentBuilder builder, BlobContainerClient containerClient, AzureBlobAgentThreadStoreOptions? options = null)
        => WithAzureBlobThreadStore(builder, sp => containerClient, options);

    /// <summary>
    /// Configures the agent builder to use Azure Blob Storage as the thread store for agent state persistence.
    /// </summary>
    /// <param name="builder">The agent builder to configure with Azure Blob thread store support.</param>
    /// <param name="createBlobContainer">A factory function that provides a configured BlobContainerClient instance for accessing the Azure Blob
    /// container used to store thread data.</param>
    /// <param name="options">Optional settings for customizing the Azure Blob thread store behavior. If null, default options are used.</param>
    /// <returns>The same agent builder instance, configured to use Azure Blob Storage for thread persistence.</returns>
    public static IHostedAgentBuilder WithAzureBlobThreadStore(
        this IHostedAgentBuilder builder,
        Func<IServiceProvider, BlobContainerClient> createBlobContainer,
        AzureBlobAgentThreadStoreOptions? options = null)
            => builder.WithThreadStore((sp, key) =>
            {
                var blobContainer = createBlobContainer(sp);
                return new AzureBlobAgentThreadStore(blobContainer, options);
            });
}
