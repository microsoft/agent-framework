// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Azure.Cosmos;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB;

#pragma warning disable VSTHRD002

/// <summary>
/// Extension methods for configuring Cosmos DB actor state storage in dependency injection.
/// </summary>
public static class ServiceCollectionExtensions
{
    /// <summary>
    /// Adds Cosmos DB actor state storage to the service collection.
    /// </summary>
    /// <param name="services">The service collection to add services to.</param>
    /// <param name="connectionString">The Cosmos DB connection string.</param>
    /// <param name="databaseName">The database name to use for actor state storage.</param>
    /// <param name="containerName">The container name to use for actor state storage. Defaults to "ActorState".</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddCosmosActorStateStorage(
        this IServiceCollection services,
        string connectionString,
        string databaseName,
        string containerName = "ActorState")
    {
        // Register CosmosClient as singleton
        services.AddSingleton(serviceProvider =>
        {
            var cosmosClientOptions = new CosmosClientOptions
            {
                ApplicationName = "AgentFramework",
                ConnectionMode = ConnectionMode.Direct,
                ConsistencyLevel = ConsistencyLevel.Session,
                UseSystemTextJsonSerializerWithOptions = new JsonSerializerOptions
                {
                    PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
                    TypeInfoResolver = CosmosActorStateJsonContext.Default
                }
            };

            return new CosmosClient(connectionString, cosmosClientOptions);
        });

        // Register LazyCosmosContainer as singleton
        services.AddSingleton(serviceProvider =>
        {
            var cosmosClient = serviceProvider.GetRequiredService<CosmosClient>();
            return new LazyCosmosContainer(cosmosClient, databaseName, containerName);
        });

        // Register the storage implementation
        services.AddSingleton<IActorStateStorage>(serviceProvider =>
        {
            var lazyContainer = serviceProvider.GetRequiredService<LazyCosmosContainer>();
            return new CosmosActorStateStorage(lazyContainer);
        });

        return services;
    }

    /// <summary>
    /// Adds Cosmos DB actor state storage to the service collection using an existing CosmosClient from DI.
    /// </summary>
    /// <param name="services">The service collection to add services to.</param>
    /// <param name="databaseName">The database name to use for actor state storage.</param>
    /// <param name="containerName">The container name to use for actor state storage. Defaults to "ActorState".</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddCosmosActorStateStorage(
        this IServiceCollection services,
        string databaseName,
        string containerName = "ActorState")
    {
        // Register LazyCosmosContainer as singleton using existing CosmosClient
        services.AddSingleton(serviceProvider =>
        {
            var cosmosClient = serviceProvider.GetRequiredService<CosmosClient>();
            return new LazyCosmosContainer(cosmosClient, databaseName, containerName);
        });

        // Register the storage implementation
        services.AddSingleton<IActorStateStorage>(serviceProvider =>
        {
            var lazyContainer = serviceProvider.GetRequiredService<LazyCosmosContainer>();
            return new CosmosActorStateStorage(lazyContainer);
        });

        return services;
    }
}
