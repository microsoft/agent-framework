// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB.Tests;

var builder = DistributedApplication.CreateBuilder(args);
var cosmosDb = builder.AddAzureCosmosDB(CosmosDBTestConstants.TestCosmosDbName);

if (CosmosDBTestConstants.UseEmulatorForTesting)
{
    cosmosDb.RunAsEmulator(emulator => emulator.WithLifetime(ContainerLifetime.Persistent));
}
else
{
    var cosmosDbResource = builder.AddParameterFromConfiguration("CosmosDbName", "CosmosDb:Name");
    var cosmosDbResourceGroup = builder.AddParameterFromConfiguration("CosmosDbResourceGroup", "CosmosDb:ResourceGroup");
    cosmosDb.RunAsExisting(cosmosDbResource, cosmosDbResourceGroup);
}

cosmosDb.AddCosmosDatabase(CosmosDBTestConstants.TestCosmosDbDatabaseName);

builder.Build().Run();
