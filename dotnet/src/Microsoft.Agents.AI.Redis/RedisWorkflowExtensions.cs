// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using StackExchange.Redis;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides extension methods for integrating Redis checkpoint storage with the Agent Framework.
/// </summary>
public static class RedisWorkflowExtensions
{
    /// <summary>
    /// Creates a Redis checkpoint store using a connection string.
    /// </summary>
    /// <param name="connectionString">The Redis connection string (e.g., "localhost:6379").</param>
    /// <param name="options">Optional configuration for the checkpoint store.</param>
    /// <returns>A new <see cref="RedisCheckpointStore"/> instance.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="connectionString"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="connectionString"/> is empty or whitespace.</exception>
    [RequiresUnreferencedCode("The RedisCheckpointStore uses JSON serialization which is incompatible with trimming.")]
    [RequiresDynamicCode("The RedisCheckpointStore uses JSON serialization which is incompatible with NativeAOT.")]
    public static RedisCheckpointStore CreateRedisCheckpointStore(
        string connectionString,
        RedisCheckpointStoreOptions? options = null)
    {
        if (string.IsNullOrWhiteSpace(connectionString))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(connectionString));
        }

        return new RedisCheckpointStore(connectionString, options);
    }

    /// <summary>
    /// Creates a Redis checkpoint store using an existing connection multiplexer.
    /// </summary>
    /// <param name="connectionMultiplexer">An existing Redis connection multiplexer.</param>
    /// <param name="options">Optional configuration for the checkpoint store.</param>
    /// <returns>A new <see cref="RedisCheckpointStore"/> instance.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="connectionMultiplexer"/> is null.</exception>
    [RequiresUnreferencedCode("The RedisCheckpointStore uses JSON serialization which is incompatible with trimming.")]
    [RequiresDynamicCode("The RedisCheckpointStore uses JSON serialization which is incompatible with NativeAOT.")]
    public static RedisCheckpointStore CreateRedisCheckpointStore(
        IConnectionMultiplexer connectionMultiplexer,
        RedisCheckpointStoreOptions? options = null)
    {
        if (connectionMultiplexer is null)
        {
            throw new ArgumentNullException(nameof(connectionMultiplexer));
        }

        return new RedisCheckpointStore(connectionMultiplexer, options);
    }

    /// <summary>
    /// Creates a Redis checkpoint store with TTL configuration.
    /// </summary>
    /// <param name="connectionString">The Redis connection string (e.g., "localhost:6379").</param>
    /// <param name="timeToLive">The Time-To-Live duration for checkpoints.</param>
    /// <param name="keyPrefix">Optional key prefix for Redis keys. Defaults to "checkpoint".</param>
    /// <returns>A new <see cref="RedisCheckpointStore"/> instance with TTL configured.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="connectionString"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="connectionString"/> is empty or whitespace.</exception>
    [RequiresUnreferencedCode("The RedisCheckpointStore uses JSON serialization which is incompatible with trimming.")]
    [RequiresDynamicCode("The RedisCheckpointStore uses JSON serialization which is incompatible with NativeAOT.")]
    public static RedisCheckpointStore CreateRedisCheckpointStoreWithTtl(
        string connectionString,
        TimeSpan timeToLive,
        string? keyPrefix = null)
    {
        if (string.IsNullOrWhiteSpace(connectionString))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(connectionString));
        }

        var options = new RedisCheckpointStoreOptions
        {
            TimeToLive = timeToLive,
            KeyPrefix = keyPrefix ?? "checkpoint"
        };

        return new RedisCheckpointStore(connectionString, options);
    }

    /// <summary>
    /// Creates a generic Redis checkpoint store using a connection string.
    /// </summary>
    /// <typeparam name="T">The type of objects to store as checkpoint values.</typeparam>
    /// <param name="connectionString">The Redis connection string (e.g., "localhost:6379").</param>
    /// <param name="options">Optional configuration for the checkpoint store.</param>
    /// <returns>A new <see cref="RedisCheckpointStore{T}"/> instance.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="connectionString"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="connectionString"/> is empty or whitespace.</exception>
    [RequiresUnreferencedCode("The RedisCheckpointStore uses JSON serialization which is incompatible with trimming.")]
    [RequiresDynamicCode("The RedisCheckpointStore uses JSON serialization which is incompatible with NativeAOT.")]
    public static RedisCheckpointStore<T> CreateRedisCheckpointStore<T>(
        string connectionString,
        RedisCheckpointStoreOptions? options = null)
    {
        if (string.IsNullOrWhiteSpace(connectionString))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(connectionString));
        }

        return new RedisCheckpointStore<T>(connectionString, options);
    }
}
