// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.AzureStorage;

/// <summary>
/// Configuration options for <see cref="AzureBlobAgentSessionStore"/>.
/// </summary>
public sealed class AzureBlobAgentSessionStoreOptions
{
    /// <summary>
    /// Gets or sets a value indicating whether to automatically create the container if it doesn't exist.
    /// </summary>
    /// <remarks>
    /// Defaults to <see langword="true"/>.
    /// Set this to <see langword="false"/> when the supplied identity has data access but cannot create containers.
    /// </remarks>
    public bool CreateContainerIfNotExists { get; set; } = true;

    /// <summary>
    /// Gets or sets the blob name prefix to use for organizing sessions.
    /// </summary>
    /// <remarks>
    /// This can be used to namespace sessions within a container.
    /// For example, setting this to "prod/" will store all blobs under a "prod/" prefix.
    /// The normalized prefix cannot exceed 886 characters.
    /// </remarks>
    public string? BlobNamePrefix { get; set; }
}
