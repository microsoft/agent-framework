// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using StackExchange.Redis;

namespace Microsoft.Agents.AI.Redis.UnitTests;

/// <summary>
/// Connects to the Redis server used by <see cref="RedisCheckpointStoreServerTests"/>.
/// </summary>
/// <remarks>
/// The server is read from the REDIS_CONNECTION_STRING environment variable and defaults to localhost:6379, for example a
/// container started with <c>docker run -d -p 6379:6379 redis:7-alpine</c>. Tests are skipped when no server is reachable,
/// unless REDIS_AVAILABLE is set to true (as in CI), in which case they fail.
/// </remarks>
public sealed class RedisFixture : IAsyncLifetime
{
    private static readonly string s_connectionString = Environment.GetEnvironmentVariable("REDIS_CONNECTION_STRING") ?? "localhost:6379";

    private ConnectionMultiplexer? _connection;

    /// <summary>
    /// Gets a value indicating whether a Redis server is reachable.
    /// </summary>
    public bool IsAvailable => this._connection is not null;

    /// <summary>
    /// Gets the shared connection to the Redis server.
    /// </summary>
    public IConnectionMultiplexer Connection => this._connection ?? throw new InvalidOperationException("Redis is not available.");

    /// <summary>
    /// Skips the calling test when no Redis server is reachable and REDIS_AVAILABLE is not set to true.
    /// </summary>
    public void SkipIfNotAvailable()
    {
        bool ciRedisAvailable = string.Equals(Environment.GetEnvironmentVariable("REDIS_AVAILABLE"), bool.TrueString, StringComparison.OrdinalIgnoreCase);

        Assert.SkipWhen(!ciRedisAvailable && !this.IsAvailable, "Redis is not available");
    }

    /// <summary>
    /// Opens a new, separate connection to the Redis server, as a different process would.
    /// </summary>
    /// <returns>A new connection. The caller disposes it.</returns>
    public static Task<ConnectionMultiplexer> ConnectAsync() => ConnectionMultiplexer.ConnectAsync(CreateConfiguration());

    /// <inheritdoc />
    public async ValueTask InitializeAsync()
    {
        try
        {
            this._connection = await ConnectAsync();
        }
        catch (RedisConnectionException)
        {
            // Redis not available, tests will be skipped
            this._connection = null;
        }
    }

    /// <inheritdoc />
    public async ValueTask DisposeAsync()
    {
        if (this._connection is not null)
        {
            await this._connection.DisposeAsync();
        }
    }

    private static ConfigurationOptions CreateConfiguration()
    {
        ConfigurationOptions configuration = ConfigurationOptions.Parse(s_connectionString);
        configuration.ConnectTimeout = 2000;
        return configuration;
    }
}

/// <summary>
/// Shares one <see cref="RedisFixture"/> between the Redis server test classes.
/// </summary>
[CollectionDefinition(Name)]
public sealed class RedisCollectionFixture : ICollectionFixture<RedisFixture>
{
    /// <summary>
    /// The name of the collection.
    /// </summary>
    public const string Name = "Redis";
}
