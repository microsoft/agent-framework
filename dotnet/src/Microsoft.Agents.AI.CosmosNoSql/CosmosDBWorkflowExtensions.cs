// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Azure.Cosmos;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides extension methods for integrating Cosmos DB checkpoint storage with the Agent Framework.
/// </summary>
public static class CosmosDBWorkflowExtensions
{
    /// <summary>
    /// Creates a Cosmos DB checkpoint store using connection string authentication.
    /// </summary>
    /// <param name="connectionString">The Cosmos DB connection string.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <returns>A new instance of <see cref="CosmosCheckpointStore"/>.</returns>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    [RequiresUnreferencedCode("The CosmosCheckpointStore uses JSON serialization which is incompatible with trimming.")]
    [RequiresDynamicCode("The CosmosCheckpointStore uses JSON serialization which is incompatible with NativeAOT.")]
    public static CosmosCheckpointStore CreateCheckpointStore(
        string connectionString,
        string databaseId,
        string containerId)
    {
        if (string.IsNullOrWhiteSpace(connectionString))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(connectionString));
        }

        if (string.IsNullOrWhiteSpace(databaseId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(databaseId));
        }

        if (string.IsNullOrWhiteSpace(containerId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(containerId));
        }

        return new CosmosCheckpointStore(connectionString, databaseId, containerId);
    }

    /// <summary>
    /// Creates a Cosmos DB checkpoint store using managed identity authentication.
    /// </summary>
    /// <param name="accountEndpoint">The Cosmos DB account endpoint URI.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <returns>A new instance of <see cref="CosmosCheckpointStore"/>.</returns>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    [RequiresUnreferencedCode("The CosmosCheckpointStore uses JSON serialization which is incompatible with trimming.")]
    [RequiresDynamicCode("The CosmosCheckpointStore uses JSON serialization which is incompatible with NativeAOT.")]
    public static CosmosCheckpointStore CreateCheckpointStoreUsingManagedIdentity(
        string accountEndpoint,
        string databaseId,
        string containerId)
    {
        if (string.IsNullOrWhiteSpace(accountEndpoint))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(accountEndpoint));
        }

        if (string.IsNullOrWhiteSpace(databaseId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(databaseId));
        }

        if (string.IsNullOrWhiteSpace(containerId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(containerId));
        }

        return new CosmosCheckpointStore(accountEndpoint, new DefaultAzureCredential(), databaseId, containerId);
    }

    /// <summary>
    /// Creates a Cosmos DB checkpoint store using an existing <see cref="CosmosClient"/>.
    /// </summary>
    /// <param name="cosmosClient">The <see cref="CosmosClient"/> instance to use for Cosmos DB operations.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <returns>A new instance of <see cref="CosmosCheckpointStore"/>.</returns>
    /// <exception cref="ArgumentNullException">Thrown when any required parameter is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    [RequiresUnreferencedCode("The CosmosCheckpointStore uses JSON serialization which is incompatible with trimming.")]
    [RequiresDynamicCode("The CosmosCheckpointStore uses JSON serialization which is incompatible with NativeAOT.")]
    public static CosmosCheckpointStore CreateCheckpointStore(
        CosmosClient cosmosClient,
        string databaseId,
        string containerId)
    {
        if (cosmosClient is null)
        {
            throw new ArgumentNullException(nameof(cosmosClient));
        }

        if (string.IsNullOrWhiteSpace(databaseId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(databaseId));
        }

        if (string.IsNullOrWhiteSpace(containerId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(containerId));
        }

        return new CosmosCheckpointStore(cosmosClient, databaseId, containerId);
    }

    /// <summary>
    /// Creates a generic Cosmos DB checkpoint store using connection string authentication.
    /// </summary>
    /// <typeparam name="T">The type of objects to store as checkpoint values.</typeparam>
    /// <param name="connectionString">The Cosmos DB connection string.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <returns>A new instance of <see cref="CosmosCheckpointStore{T}"/>.</returns>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    [RequiresUnreferencedCode("The CosmosCheckpointStore uses JSON serialization which is incompatible with trimming.")]
    [RequiresDynamicCode("The CosmosCheckpointStore uses JSON serialization which is incompatible with NativeAOT.")]
    public static CosmosCheckpointStore<T> CreateCheckpointStore<T>(
        string connectionString,
        string databaseId,
        string containerId)
    {
        if (string.IsNullOrWhiteSpace(connectionString))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(connectionString));
        }

        if (string.IsNullOrWhiteSpace(databaseId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(databaseId));
        }

        if (string.IsNullOrWhiteSpace(containerId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(containerId));
        }

        return new CosmosCheckpointStore<T>(connectionString, databaseId, containerId);
    }

    /// <summary>
    /// Creates a generic Cosmos DB checkpoint store using managed identity authentication.
    /// </summary>
    /// <typeparam name="T">The type of objects to store as checkpoint values.</typeparam>
    /// <param name="accountEndpoint">The Cosmos DB account endpoint URI.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <returns>A new instance of <see cref="CosmosCheckpointStore{T}"/>.</returns>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    [RequiresUnreferencedCode("The CosmosCheckpointStore uses JSON serialization which is incompatible with trimming.")]
    [RequiresDynamicCode("The CosmosCheckpointStore uses JSON serialization which is incompatible with NativeAOT.")]
    public static CosmosCheckpointStore<T> CreateCheckpointStoreUsingManagedIdentity<T>(
        string accountEndpoint,
        string databaseId,
        string containerId)
    {
        if (string.IsNullOrWhiteSpace(accountEndpoint))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(accountEndpoint));
        }

        if (string.IsNullOrWhiteSpace(databaseId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(databaseId));
        }

        if (string.IsNullOrWhiteSpace(containerId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(containerId));
        }

        return new CosmosCheckpointStore<T>(accountEndpoint, new DefaultAzureCredential(), databaseId, containerId);
    }

    /// <summary>
    /// Creates a generic Cosmos DB checkpoint store using an existing <see cref="CosmosClient"/>.
    /// </summary>
    /// <typeparam name="T">The type of objects to store as checkpoint values.</typeparam>
    /// <param name="cosmosClient">The <see cref="CosmosClient"/> instance to use for Cosmos DB operations.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <returns>A new instance of <see cref="CosmosCheckpointStore{T}"/>.</returns>
    /// <exception cref="ArgumentNullException">Thrown when any required parameter is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    [RequiresUnreferencedCode("The CosmosCheckpointStore uses JSON serialization which is incompatible with trimming.")]
    [RequiresDynamicCode("The CosmosCheckpointStore uses JSON serialization which is incompatible with NativeAOT.")]
    public static CosmosCheckpointStore<T> CreateCheckpointStore<T>(
        CosmosClient cosmosClient,
        string databaseId,
        string containerId)
    {
        if (cosmosClient is null)
        {
            throw new ArgumentNullException(nameof(cosmosClient));
        }

        if (string.IsNullOrWhiteSpace(databaseId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(databaseId));
        }

        if (string.IsNullOrWhiteSpace(containerId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(containerId));
        }

        return new CosmosCheckpointStore<T>(cosmosClient, databaseId, containerId);
    }
}
