// Copyright (c) Microsoft. All rights reserved.

using System;
using Azure.Storage.Blobs;
using Microsoft.Agents.AI.Hosting.AzureStorage;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides hosted agent registration extensions for Azure Blob Storage session persistence.
/// </summary>
public static class AzureBlobHostedAgentBuilderExtensions
{
    /// <summary>
    /// Configures a hosted agent to persist sessions in an Azure Blob Storage container.
    /// </summary>
    /// <param name="builder">The hosted agent builder to configure.</param>
    /// <param name="containerClient">The Blob container client used to store sessions.</param>
    /// <param name="options">Optional session store configuration.</param>
    /// <param name="withIsolation">
    /// Whether to scope session IDs with the configured <see cref="AgentIsolationKeyProvider"/>.
    /// </param>
    /// <returns>The supplied <paramref name="builder"/>.</returns>
    public static IHostedAgentBuilder WithAzureBlobSessionStore(
        this IHostedAgentBuilder builder,
        BlobContainerClient containerClient,
        AzureBlobAgentSessionStoreOptions? options = null,
        bool withIsolation = true)
    {
        Throw.IfNull(builder);
        Throw.IfNull(containerClient);

        return builder.WithAzureBlobSessionStore(
            (_, _) => containerClient,
            options,
            ServiceLifetime.Singleton,
            withIsolation);
    }

    /// <summary>
    /// Configures a hosted agent to persist sessions in an Azure Blob Storage container supplied by a factory.
    /// </summary>
    /// <param name="builder">The hosted agent builder to configure.</param>
    /// <param name="createBlobContainerClient">
    /// A factory that receives the service provider and stable hosted agent registration name.
    /// </param>
    /// <param name="options">Optional session store configuration.</param>
    /// <param name="lifetime">The dependency injection lifetime of the registered session store.</param>
    /// <param name="withIsolation">
    /// Whether to scope session IDs with the configured <see cref="AgentIsolationKeyProvider"/>.
    /// </param>
    /// <returns>The supplied <paramref name="builder"/>.</returns>
    public static IHostedAgentBuilder WithAzureBlobSessionStore(
        this IHostedAgentBuilder builder,
        Func<IServiceProvider, string, BlobContainerClient> createBlobContainerClient,
        AzureBlobAgentSessionStoreOptions? options = null,
        ServiceLifetime lifetime = ServiceLifetime.Singleton,
        bool withIsolation = true)
    {
        Throw.IfNull(builder);
        Throw.IfNull(createBlobContainerClient);

        return builder.WithSessionStore(
            (serviceProvider, agentName) =>
            {
                BlobContainerClient containerClient =
                    Throw.IfNull(createBlobContainerClient(serviceProvider, agentName));
                return new AzureBlobAgentSessionStore(containerClient, agentName, options);
            },
            lifetime,
            withIsolation);
    }
}
