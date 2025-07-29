// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.ObjectModel;
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
        services.AddSingleton<CosmosClient>(serviceProvider =>
        {
            var cosmosClientOptions = new CosmosClientOptions
            {
                ApplicationName = "AgentFramework",
                ConnectionMode = ConnectionMode.Direct,
                ConsistencyLevel = ConsistencyLevel.Session,
                UseSystemTextJsonSerializerWithOptions = new JsonSerializerOptions()
                {
                    PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
                }
            };

            return new CosmosClient(connectionString, cosmosClientOptions);
        });

        // Register Container as singleton
        services.AddSingleton<Container>(serviceProvider =>
        {
            var cosmosClient = serviceProvider.GetRequiredService<CosmosClient>();

            // Create database and container if they don't exist
            var database = cosmosClient.CreateDatabaseIfNotExistsAsync(databaseName).GetAwaiter().GetResult();

            var containerProperties = new ContainerProperties(containerName, "/actorId")
            {
                Id = containerName,
                IndexingPolicy = new IndexingPolicy
                {
                    IndexingMode = IndexingMode.Consistent,
                    Automatic = true
                },
                PartitionKeyPaths = ["/actorId"]
            };

            // Add composite index for efficient queries
            containerProperties.IndexingPolicy.CompositeIndexes.Add(new Collection<CompositePath>
            {
                new() { Path = "/actorId", Order = CompositePathSortOrder.Ascending },
                new() { Path = "/key", Order = CompositePathSortOrder.Ascending }
            });

            var container = database.Database.CreateContainerIfNotExistsAsync(containerProperties).GetAwaiter().GetResult();
            return container.Container;
        });

        // Register the storage implementation
        services.AddSingleton<IActorStateStorage, CosmosActorStateStorage>();

        return services;
    }

    /// <summary>
    /// Adds Cosmos DB actor state storage to the service collection with a factory for the Container.
    /// </summary>
    /// <param name="services">The service collection to add services to.</param>
    /// <param name="containerFactory">A factory function that creates the Cosmos Container.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddCosmosActorStateStorage(
        this IServiceCollection services,
        Func<IServiceProvider, Container> containerFactory)
    {
        services.AddSingleton<Container>(containerFactory);
        services.AddSingleton<IActorStateStorage, CosmosActorStateStorage>();
        return services;
    }

    /// <summary>
    /// Adds Cosmos DB actor state storage to the service collection using an existing Container registration.
    /// </summary>
    /// <param name="services">The service collection to add services to.</param>
    /// <returns>The service collection for chaining.</returns>
    /// <remarks>
    /// This overload assumes that a <see cref="Container"/> is already registered in the service collection.
    /// </remarks>
    public static IServiceCollection AddCosmosActorStateStorage(this IServiceCollection services)
    {
        services.AddSingleton<IActorStateStorage, CosmosActorStateStorage>();
        return services;
    }
}
