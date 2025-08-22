// Copyright (c) Microsoft. All rights reserved.

//using System.Linq.Expressions;

namespace CosmosDB.Testing.AppHost;

public static class CosmosDBTestConstants
{
    public const string TestCosmosDbName = "ActorStateStorageTests";
    public const string TestCosmosDbDatabaseName = "state-database";

    //Set to use the CosmosDB emulator for testing via environment variable.
    //Example: set COSMOSDB_TESTS_USE_EMULATOR = true in your environment.
    //Warning: Using the emulator may cause test flakiness.
    public static bool UseAspireEmulatorForTesting => string.Equals(
        Environment.GetEnvironmentVariable("COSMOSDB_TESTS_USE_EMULATOR"),
        "true",
        StringComparison.OrdinalIgnoreCase);

    public static bool UseEmulatorInCICD => string.Equals(
        Environment.GetEnvironmentVariable("COSMOSDB_TESTS_USE_EMULATOR_CICD"),
        "true",
        StringComparison.OrdinalIgnoreCase);
}
