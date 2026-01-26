// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading.Tasks;
using Azure.Core;
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
    [RequiresUnreferencedCode("The CosmosChatHistoryProvider uses JSON serialization which is incompatible with trimming.")]
    [RequiresDynamicCode("The CosmosChatHistoryProvider uses JSON serialization which is incompatible with NativeAOT.")]
    public static ChatClientAgentOptions WithCosmosDBChatHistoryProvider(
        this ChatClientAgentOptions options,
        string connectionString,
        string databaseId,
        string containerId)
    {
        if (options is null)
        {
            throw new ArgumentNullException(nameof(options));
        }

        options.ChatHistoryProviderFactory = (context, ct) => new ValueTask<ChatHistoryProvider>(new CosmosChatHistoryProvider(connectionString, databaseId, containerId));
        return options;
    }

    /// <summary>
    /// Configures the agent to use Cosmos DB for message storage with managed identity authentication.
    /// </summary>
    /// <param name="options">The chat client agent options to configure.</param>
    /// <param name="accountEndpoint">The Cosmos DB account endpoint URI.</param>
    /// <param name="databaseId">The identifier of the Cosmos DB database.</param>
    /// <param name="containerId">The identifier of the Cosmos DB container.</param>
    /// <param name="tokenCredential">The TokenCredential to use for authentication (e.g., DefaultAzureCredential, ManagedIdentityCredential).</param>
    /// <returns>The configured <see cref="ChatClientAgentOptions"/>.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="options"/> or <paramref name="tokenCredential"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when any string parameter is null or whitespace.</exception>
    [RequiresUnreferencedCode("The CosmosChatHistoryProvider uses JSON serialization which is incompatible with trimming.")]
    [RequiresDynamicCode("The CosmosChatHistoryProvider uses JSON serialization which is incompatible with NativeAOT.")]
    public static ChatClientAgentOptions WithCosmosDBChatHistoryProviderUsingManagedIdentity(
        this ChatClientAgentOptions options,
        string accountEndpoint,
        string databaseId,
        string containerId,
        TokenCredential tokenCredential)
    {
        if (options is null)
        {
            throw new ArgumentNullException(nameof(options));
        }

        if (tokenCredential is null)
        {
            throw new ArgumentNullException(nameof(tokenCredential));
        }

        options.ChatHistoryProviderFactory = (context, ct) => new ValueTask<ChatHistoryProvider>(new CosmosChatHistoryProvider(accountEndpoint, tokenCredential, databaseId, containerId));
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
    [RequiresUnreferencedCode("The CosmosChatHistoryProvider uses JSON serialization which is incompatible with trimming.")]
    [RequiresDynamicCode("The CosmosChatHistoryProvider uses JSON serialization which is incompatible with NativeAOT.")]
    public static ChatClientAgentOptions WithCosmosDBChatHistoryProvider(
        this ChatClientAgentOptions options,
        CosmosClient cosmosClient,
        string databaseId,
        string containerId)
    {
        if (options is null)
        {
            throw new ArgumentNullException(nameof(options));
        }

        options.ChatHistoryProviderFactory = (context, ct) => new ValueTask<ChatHistoryProvider>(new CosmosChatHistoryProvider(cosmosClient, databaseId, containerId));
        return options;
    }
}
