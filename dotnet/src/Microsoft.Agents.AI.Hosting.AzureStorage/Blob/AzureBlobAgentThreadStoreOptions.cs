// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.AzureStorage.Blob;

/// <summary>
/// Configuration options for <see cref="AzureBlobAgentThreadStore"/>.
/// </summary>
public sealed class AzureBlobAgentThreadStoreOptions
{
    /// <summary>
    /// Gets or sets a value indicating whether to automatically create the container if it doesn't exist.
    /// </summary>
    /// <remarks>
    /// Defaults to <see langword="true"/>.
    /// </remarks>
    public bool CreateContainerIfNotExists { get; set; } = true;

    /// <summary>
    /// Gets or sets the blob name prefix to use for organizing threads.
    /// </summary>
    /// <remarks>
    /// This can be used to namespace threads within a container.
    /// For example, setting this to "prod/" will store all blobs under a "prod/" prefix.
    /// </remarks>
    public string? BlobNamePrefix { get; set; }
}
