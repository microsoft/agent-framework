// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB.Options;

/// <summary>
/// Configuration options for Cosmos DB actor state storage.
/// </summary>
public class CosmosActorStateStorageOptions
{
    /// <summary>
    /// Gets or sets the retry configuration for container initialization.
    /// </summary>
    public RetryOptions Retry { get; set; } = new();

    /// <summary>
    /// Retry configuration options for Cosmos DB operations.
    /// </summary>
    public class RetryOptions
    {
        /// <summary>
        /// Gets or sets the maximum number of retry attempts for container initialization.
        /// Default is 3.
        /// </summary>
        public int MaxRetryAttempts { get; set; } = 3;

        /// <summary>
        /// Gets or sets the base delay for exponential backoff between retry attempts.
        /// Default is 1 second.
        /// </summary>
        public TimeSpan BaseDelay { get; set; } = TimeSpan.FromSeconds(1);

        /// <summary>
        /// Gets or sets the maximum delay between retry attempts.
        /// Default is 30 seconds.
        /// </summary>
        public TimeSpan MaxDelay { get; set; } = TimeSpan.FromSeconds(30);

        /// <summary>
        /// Gets or sets the backoff multiplier for exponential backoff.
        /// Default is 2.0.
        /// </summary>
        public double BackoffMultiplier { get; set; } = 2.0;
    }
}
