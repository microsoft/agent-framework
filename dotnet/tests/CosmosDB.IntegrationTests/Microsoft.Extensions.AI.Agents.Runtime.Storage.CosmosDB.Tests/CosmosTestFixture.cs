// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Aspire.Hosting;
using Azure.Identity;
using CosmosDB.Testing.AppHost;
using Microsoft.Azure.Cosmos;
using Microsoft.Extensions.Logging;
using static System.Net.WebRequestMethods;

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
            .CreateAsync<Projects.CosmosDB_Testing_AppHost>(cancellationToken);

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
        if (CosmosDBTestConstants.UseEmulatorForTesting && CosmosDBTestConstants.RunningCosmosDbTestsInCICD)
        {
            // Use well-known emulator connection string in CI/CD to avoid issues with environment variables.
            // https://learn.microsoft.com/en-us/azure/cosmos-db/emulator
            cs = "AccountEndpoint=https://localhost:8081/;AccountKey=C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw==;";
        }

        CosmosClientOptions ccoptions = new()
        {
            UseSystemTextJsonSerializerWithOptions = new JsonSerializerOptions()
            {
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
                TypeInfoResolver = CosmosActorStateJsonContext.Default
            },
            HttpClientFactory = () =>
            {
                HttpMessageHandler httpMessageHandler = new HttpClientHandler()
                {
                    // ignore SSL errors for testing with emulator
                    ServerCertificateCustomValidationCallback = (req, cert, chain, errors) => true
                };
                return new HttpClient(httpMessageHandler);
            },
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
        var db = await this.CosmosClient.CreateDatabaseIfNotExistsAsync(CosmosDBTestConstants.TestCosmosDbDatabaseName);

        var containerProperties = new ContainerProperties()
        {
            Id = "CosmosActorStateStorageTests",
            PartitionKeyPaths = LazyCosmosContainer.CosmosPartitionKeyPaths
        };

        try
        {
            this.Container = await database.CreateContainerIfNotExistsAsync(containerProperties);
        }
        catch (Exception ex)
        {
            throw new ArgumentException($"Initialization error. Cosmos ConnectionString: {cs}; ENV: useEmulator={CosmosDBTestConstants.UseEmulatorForTesting};CICD={CosmosDBTestConstants.RunningCosmosDbTestsInCICD}", ex);
        }
    }

    public async Task DisposeAsync()
    {
        await this.App.DisposeAsync();
        this.CosmosClient.Dispose();
    }
}
