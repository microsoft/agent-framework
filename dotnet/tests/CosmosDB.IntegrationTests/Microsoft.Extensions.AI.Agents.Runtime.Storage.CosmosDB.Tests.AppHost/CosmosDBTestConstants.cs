// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB.Tests;

internal static class CosmosDBTestConstants
{
    public static string TestCosmosDbName = "ActorStateStorageTests";
    public static string TestCosmosDbDatabaseName = "state-database";

    // Set to use the CosmosDB emulator for testing.
    // Warning: Using the emulator may cause test flakiness.
    public static bool UseEmulatorForTesting = false;
}
