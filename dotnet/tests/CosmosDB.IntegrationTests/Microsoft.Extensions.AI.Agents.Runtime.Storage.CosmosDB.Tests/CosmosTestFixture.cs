// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Aspire.Hosting;
using Azure.Identity;
using CosmosDB.Testing.AppHost;
using Microsoft.Azure.Cosmos;
using Microsoft.Extensions.Logging;

#pragma warning disable CA2007, VSTHRD111, CS1591

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB.Tests;

[CollectionDefinition("Cosmos Test Collection")]
public class CosmosTests : ICollectionFixture<CosmosTestFixture>;

/// <summary>
/// Shared test fixture for CosmosDB integration tests.
/// Sets up and manages the CosmosDB container for all tests.
/// </summary>
public class CosmosTestFixture : IAsyncLifetime
{
    public DistributedApplication App { get; private set; } = default!;
    public CosmosClient CosmosClient { get; private set; } = default!;
    public Container Container { get; private set; } = default!;

    /// <inheritdoc/>
    public async Task InitializeAsync()
    {
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(300));
        var cancellationToken = cts.Token;

        var appHost = await DistributedApplicationTestingBuilder
            .CreateAsync<Projects.CosmosDB_Testing_AppHost>(cancellationToken);

        appHost.Services.AddLogging(logging =>
        {
            logging.SetMinimumLevel(LogLevel.Debug);
            logging.AddFilter(appHost.Environment.ApplicationName, LogLevel.Debug);
            logging.AddFilter("Aspire.", LogLevel.Debug);
        });

        appHost.Services.ConfigureHttpClientDefaults(clientBuilder =>
            clientBuilder.AddStandardResilienceHandler());

        this.App = await appHost.BuildAsync(cancellationToken).WaitAsync(cancellationToken);
        await this.App.StartAsync(cancellationToken).WaitAsync(cancellationToken);

        var connectionString = await this.App.GetConnectionStringAsync(CosmosDBTestConstants.TestCosmosDbName, cancellationToken);
        if (CosmosDBTestConstants.UseEmulatorInCICD)
        {
            // Emulator is setup in the CI/CD pipeline, so we will not use one produced by Aspire.
            // For simplicity, we override the connection string here with the well-known emulator connection string.
            // https://learn.microsoft.com/en-us/azure/cosmos-db/emulator

            connectionString = "AccountEndpoint=https://localhost:8081/;AccountKey=C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw==;";
        }

        CosmosClientOptions ccoptions = new()
        {
            UseSystemTextJsonSerializerWithOptions = new JsonSerializerOptions()
            {
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
                TypeInfoResolver = CosmosActorStateJsonContext.Default
            }
        };

        if (CosmosDBTestConstants.UseAspireEmulatorForTesting || CosmosDBTestConstants.UseEmulatorInCICD)
        {
            ccoptions.ConnectionMode = ConnectionMode.Gateway;
            ccoptions.LimitToEndpoint = true;
            this.CosmosClient = new CosmosClient(connectionString, ccoptions);
        }
        else
        {
            this.CosmosClient = new CosmosClient(connectionString, new DefaultAzureCredential(), ccoptions);
        }

        var database = this.CosmosClient.GetDatabase(CosmosDBTestConstants.TestCosmosDbDatabaseName);

        // raise throughput to avoid parallel test execution failures
        var throughputProperties = ThroughputProperties.CreateAutoscaleThroughput(100000);

        // Ensure database exists. It will be a no-op if it was already created before.
        _ = await this.CosmosClient.CreateDatabaseIfNotExistsAsync(CosmosDBTestConstants.TestCosmosDbDatabaseName, throughputProperties);

        var containerProperties = new ContainerProperties()
        {
            Id = "CosmosActorStateStorageTests",
            PartitionKeyPaths = LazyCosmosContainer.CosmosPartitionKeyPaths
        };

        this.Container = await database.CreateContainerIfNotExistsAsync(containerProperties);
    }

    public async Task DisposeAsync()
    {
        await this.App.DisposeAsync();
        this.CosmosClient.Dispose();
    }
}
