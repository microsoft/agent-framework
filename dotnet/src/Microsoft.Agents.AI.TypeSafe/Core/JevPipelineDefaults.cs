// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Assigns the pipeline defaults of the official TypeSafe SDK to the options of every Jev client.
/// </summary>
internal static class JevPipelineDefaults
{
    public const string DefaultEndpoint = "https://api.typesafe.ai/v1/systemone";
    public const string DefaultModelId = "jev-latest";

    private static readonly TimeSpan s_defaultNetworkTimeout = TimeSpan.FromSeconds(10);

    /// <summary>
    /// Sets the SDK retry policy and network timeout where the caller left them unset.
    /// </summary>
    /// <remarks>
    /// Call this from <see cref="ClientPipelineOptions.Freeze"/>, not from a constructor, because
    /// <see cref="ClientPipelineOptions.ClientLoggingOptions"/> may be set after construction. ClientPipeline.Create
    /// freezes the options before it reads them, so the defaults are in place when the pipeline is built.
    /// </remarks>
    public static void Apply(ClientPipelineOptions options)
    {
        options.RetryPolicy ??= new JevRetryPolicy(
            JevRetryPolicy.DefaultMaxRetries,
            options.ClientLoggingOptions?.EnableLogging ?? true,
            options.ClientLoggingOptions?.LoggerFactory);
        options.NetworkTimeout ??= s_defaultNetworkTimeout;
    }
}
