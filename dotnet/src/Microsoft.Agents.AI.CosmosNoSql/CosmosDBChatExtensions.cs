// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Azure.Identity;
using Microsoft.Azure.Cosmos;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides extension methods for integrating Cosmos DB chat message storage with the Agent Framework.
/// </summary>
public static class CosmosDBChatExtensions
{
    /// <summary>
    /// Configures the agent to use Cosmos DB for message storage with connection string authentication.
    /// </summary>
    /// <param name="options">The chat client agent options to configure.</param>
    /// <param name="connectionString">The Cosmos DB connection string.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <returns>The configured <see cref="ChatClientAgentOptions"/>.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="options"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    [RequiresUnreferencedCode("The CosmosChatMessageStore uses JSON serialization which is incompatible with trimming.")]
    [RequiresDynamicCode("The CosmosChatMessageStore uses JSON serialization which is incompatible with NativeAOT.")]
    public static ChatClientAgentOptions WithCosmosDBMessageStore(
        this ChatClientAgentOptions options,
        string connectionString,
        string databaseId,
        string containerId)
    {
        if (options is null)
        {
            throw new ArgumentNullException(nameof(options));
        }

        options.ChatMessageStoreFactory = context => new CosmosChatMessageStore(connectionString, databaseId, containerId);
        return options;
    }

    /// <summary>
    /// Configures the agent to use Cosmos DB for message storage with managed identity authentication.
    /// </summary>
    /// <param name="options">The chat client agent options to configure.</param>
    /// <param name="accountEndpoint">The Cosmos DB account endpoint URI.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <returns>The configured <see cref="ChatClientAgentOptions"/>.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="options"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    [RequiresUnreferencedCode("The CosmosChatMessageStore uses JSON serialization which is incompatible with trimming.")]
    [RequiresDynamicCode("The CosmosChatMessageStore uses JSON serialization which is incompatible with NativeAOT.")]
    public static ChatClientAgentOptions WithCosmosDBMessageStoreUsingManagedIdentity(
        this ChatClientAgentOptions options,
        string accountEndpoint,
        string databaseId,
        string containerId)
    {
        if (options is null)
        {
            throw new ArgumentNullException(nameof(options));
        }

        options.ChatMessageStoreFactory = context => new CosmosChatMessageStore(accountEndpoint, new DefaultAzureCredential(), databaseId, containerId);
        return options;
    }

    /// <summary>
    /// Configures the agent to use Cosmos DB for message storage with an existing <see cref="CosmosClient"/>.
    /// </summary>
    /// <param name="options">The chat client agent options to configure.</param>
    /// <param name="cosmosClient">The <see cref="CosmosClient"/> instance to use for Cosmos DB operations.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <returns>The configured <see cref="ChatClientAgentOptions"/>.</returns>
    /// <exception cref="ArgumentNullException">Thrown when any required parameter is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    [RequiresUnreferencedCode("The CosmosChatMessageStore uses JSON serialization which is incompatible with trimming.")]
    [RequiresDynamicCode("The CosmosChatMessageStore uses JSON serialization which is incompatible with NativeAOT.")]
    public static ChatClientAgentOptions WithCosmosDBMessageStore(
        this ChatClientAgentOptions options,
        CosmosClient cosmosClient,
        string databaseId,
        string containerId)
    {
        if (options is null)
        {
            throw new ArgumentNullException(nameof(options));
        }

        options.ChatMessageStoreFactory = context => new CosmosChatMessageStore(cosmosClient, databaseId, containerId);
        return options;
    }
}
