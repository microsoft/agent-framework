// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Redis.UnitTests;

/// <summary>
/// Defines a collection fixture for Redis tests to ensure they run sequentially.
/// This prevents race conditions and resource conflicts when tests create and delete
/// data in Redis.
/// </summary>
[CollectionDefinition("Redis", DisableParallelization = true)]
public sealed class RedisCollectionFixture
{
}
