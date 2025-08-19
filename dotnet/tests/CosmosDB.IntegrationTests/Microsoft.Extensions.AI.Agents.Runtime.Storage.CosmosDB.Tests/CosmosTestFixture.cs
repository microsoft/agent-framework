// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Aspire.Hosting;
using Azure.Identity;
using Microsoft.Azure.Cosmos;
using Microsoft.Extensions.Logging;

#pragma warning disable CA2007, VSTHRD111, CS1591

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB.Tests;

[CollectionDefinition("Cosmos Test Collection")]
public class CosmosTests : ICollectionFixture<CosmosTestFixture> { }

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
            .CreateAsync<Projects.Microsoft_Extensions_AI_Agents_Runtime_Storage_CosmosDB_Tests_AppHost>(cancellationToken);

        appHost.Services.AddLogging(logging =>
        {
            logging.SetMinimumLevel(LogLevel.Debug);
            logging.AddFilter(appHost.Environment.ApplicationName, LogLevel.Debug);
            logging.AddFilter("Aspire.", LogLevel.Debug);
        });

        appHost.Services.ConfigureHttpClientDefaults(clientBuilder =>
        {
            clientBuilder.AddStandardResilienceHandler();
        });

        this.App = await appHost.BuildAsync(cancellationToken).WaitAsync(cancellationToken);
        await this.App.StartAsync(cancellationToken).WaitAsync(cancellationToken);

        var cs = await this.App.GetConnectionStringAsync(CosmosDBTestConstants.TestCosmosDbName, cancellationToken);
        CosmosClientOptions ccoptions = new()
        {
            UseSystemTextJsonSerializerWithOptions = new JsonSerializerOptions()
            {
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
                TypeInfoResolver = CosmosActorStateJsonContext.Default
            }
        };

        if (CosmosDBTestConstants.UseEmulatorForTesting)
        {
            ccoptions.ConnectionMode = ConnectionMode.Gateway;
            ccoptions.LimitToEndpoint = true;
            this.CosmosClient = new CosmosClient(cs, ccoptions);
        }
        else
        {
            this.CosmosClient = new CosmosClient(cs, new DefaultAzureCredential(), ccoptions);
        }

        var database = this.CosmosClient.GetDatabase(CosmosDBTestConstants.TestCosmosDbDatabaseName);

        var containerProperties = new ContainerProperties()
        {
            Id = "CosmosActorStateStorageTests",
            PartitionKeyPath = "/actorId"
        };

        this.Container = await database.CreateContainerIfNotExistsAsync(containerProperties);
    }

    public async Task DisposeAsync()
    {
        await this.App.DisposeAsync();
        this.CosmosClient.Dispose();
    }
}
