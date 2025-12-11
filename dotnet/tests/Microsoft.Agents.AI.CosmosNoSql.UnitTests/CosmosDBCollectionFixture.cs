// Copyright (c) Microsoft. All rights reserved.

using Xunit;

namespace Microsoft.Agents.AI.CosmosNoSql.UnitTests;

/// <summary>
/// Defines a collection fixture for Cosmos DB tests to ensure they run sequentially.
/// This prevents race conditions and resource conflicts when tests create and delete
/// databases in the Cosmos DB Emulator.
/// </summary>
[CollectionDefinition("CosmosDB", DisableParallelization = true)]
public sealed class CosmosDBCollectionFixture
{
    // This class has no code, and is never created. Its purpose is simply
    // to be the place to apply [CollectionDefinition] and all the
    // ICollectionFixture<> interfaces.
}
