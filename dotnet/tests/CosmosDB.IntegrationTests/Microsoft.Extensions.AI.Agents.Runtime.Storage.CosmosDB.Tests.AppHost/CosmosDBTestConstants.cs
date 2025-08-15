// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB.Tests;

public static class CosmosDBTestConstants
{
    public const string TestCosmosDbName = "ActorStateStorageTests";
    public const string TestCosmosDbDatabaseName = "state-database";

    // Set to use the CosmosDB emulator for testing via environment variable.
    // Example: set COSMOSDB_TESTS_USE_EMULATOR=true in your environment.
    // Warning: Using the emulator may cause test flakiness.
    public static bool UseEmulatorForTesting =>
        string.Equals(
            Environment.GetEnvironmentVariable("COSMOSDB_TESTS_USE_EMULATOR"),
            "true",
            StringComparison.OrdinalIgnoreCase);
}
