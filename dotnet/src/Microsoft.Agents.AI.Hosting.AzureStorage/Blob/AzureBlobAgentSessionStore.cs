// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure;
using Azure.Storage.Blobs;
using Azure.Storage.Blobs.Models;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.AzureStorage;

/// <summary>
/// Provides an Azure Blob Storage implementation of <see cref="AgentSessionStore"/>.
/// </summary>
/// <remarks>
/// <para>
/// The <c>agentNamespace</c> supplied to the constructor forms a stable storage partition and must remain the same
/// across application restarts. Hosted agent registration extensions supply the hosted agent registration name.
/// </para>
/// <para>
/// Serialized sessions can contain conversation content and personally identifiable information. Configure the
/// container with appropriate access controls, encryption, retention, and deletion policies. Hosts serving multiple
/// users should register this store through <c>WithAzureBlobSessionStore</c>, which enables isolation-key scoping by
/// default.
/// </para>
/// </remarks>
public sealed class AzureBlobAgentSessionStore : AgentSessionStore
{
    private const int MaxBlobNameLength = 1024;
    private const int BaseBlobNameLength = 137;

    private static readonly BlobUploadOptions s_uploadOptions = new()
    {
        HttpHeaders = new BlobHttpHeaders { ContentType = "application/json" },
    };

    private readonly BlobContainerClient _containerClient;
    private readonly object _containerInitializationLock = new();
    private readonly string _agentKey;
    private readonly string? _blobNamePrefix;
    private readonly bool _createContainerIfNotExists;
    private Task? _containerInitializationTask;

    /// <summary>
    /// Initializes a new instance of the <see cref="AzureBlobAgentSessionStore"/> class.
    /// </summary>
    /// <param name="containerClient">The blob container client to use for storage operations.</param>
    /// <param name="agentNamespace">A stable name that identifies the agent across application restarts.</param>
    /// <param name="options">Optional configuration options. If <see langword="null"/>, default options will be used.</param>
    /// <exception cref="ArgumentNullException"><paramref name="containerClient"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="agentNamespace"/> is empty or consists only of whitespace.</exception>
    /// <exception cref="ArgumentException"><paramref name="options"/> specifies a Blob name prefix that exceeds the Azure Blob name limit.</exception>
    public AzureBlobAgentSessionStore(
        BlobContainerClient containerClient,
        string agentNamespace,
        AzureBlobAgentSessionStoreOptions? options = null)
    {
        this._containerClient = Throw.IfNull(containerClient);
        this._agentKey = ComputeKey(Throw.IfNullOrWhitespace(agentNamespace));

        options ??= new AzureBlobAgentSessionStoreOptions();
        this._createContainerIfNotExists = options.CreateContainerIfNotExists;
        this._blobNamePrefix = NormalizePrefix(options.BlobNamePrefix);

        if (this._blobNamePrefix is { Length: > MaxBlobNameLength - BaseBlobNameLength - 1 })
        {
            throw new ArgumentException(
                $"The Blob name prefix must not exceed {MaxBlobNameLength - BaseBlobNameLength - 1} characters.",
                nameof(options));
        }
    }

    /// <inheritdoc />
    public override async ValueTask SaveSessionAsync(
        AIAgent agent,
        string sessionStoreId,
        AgentSession session,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);
        Throw.IfNull(sessionStoreId);
        Throw.IfNull(session);

        await this.EnsureContainerExistsAsync(cancellationToken).ConfigureAwait(false);

        JsonElement serializedSession = await agent.SerializeSessionAsync(session, cancellationToken: cancellationToken).ConfigureAwait(false);
        BlobClient blobClient = this._containerClient.GetBlobClient(this.GetBlobName(sessionStoreId));
        await blobClient.UploadAsync(
            BinaryData.FromString(serializedSession.GetRawText()),
            s_uploadOptions,
            cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public override async ValueTask<AgentSession> GetSessionAsync(
        AIAgent agent,
        string sessionStoreId,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);
        Throw.IfNull(sessionStoreId);

        await this.EnsureContainerExistsAsync(cancellationToken).ConfigureAwait(false);

        BlobClient blobClient = this._containerClient.GetBlobClient(this.GetBlobName(sessionStoreId));

        try
        {
            Response<BlobDownloadResult> response = await blobClient.DownloadContentAsync(cancellationToken).ConfigureAwait(false);
            using JsonDocument document = JsonDocument.Parse(response.Value.Content);
            return await agent.DeserializeSessionAsync(document.RootElement, cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        catch (RequestFailedException ex) when (ex.ErrorCode == BlobErrorCode.BlobNotFound.ToString())
        {
            return await agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
        }
    }

    /// <inheritdoc />
    public override async ValueTask DeleteSessionAsync(
        AIAgent agent,
        string sessionStoreId,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);
        Throw.IfNull(sessionStoreId);

        BlobClient blobClient = this._containerClient.GetBlobClient(this.GetBlobName(sessionStoreId));

        try
        {
            await blobClient.DeleteIfExistsAsync(
                DeleteSnapshotsOption.IncludeSnapshots,
                cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        catch (RequestFailedException ex) when (ex.ErrorCode == BlobErrorCode.ContainerNotFound.ToString())
        {
            // A missing container cannot contain the requested session, so deletion remains idempotent.
        }
    }

    private async Task EnsureContainerExistsAsync(CancellationToken cancellationToken)
    {
        if (!this._createContainerIfNotExists)
        {
            return;
        }

        Task initializationTask;
        lock (this._containerInitializationLock)
        {
            initializationTask = this._containerInitializationTask ??= this.CreateContainerIfNotExistsAsync();
        }

        try
        {
            await initializationTask.WaitAsync(cancellationToken).ConfigureAwait(false);
        }
        catch when (initializationTask.IsFaulted || initializationTask.IsCanceled)
        {
            lock (this._containerInitializationLock)
            {
                if (ReferenceEquals(this._containerInitializationTask, initializationTask))
                {
                    this._containerInitializationTask = null;
                }
            }

            throw;
        }
    }

    private async Task CreateContainerIfNotExistsAsync()
        => await this._containerClient.CreateIfNotExistsAsync(cancellationToken: CancellationToken.None).ConfigureAwait(false);

    private string GetBlobName(string sessionStoreId)
    {
        string sessionKey = ComputeKey(sessionStoreId);
        string baseName = $"v1/{this._agentKey}/{sessionKey}.json";

        return this._blobNamePrefix is null
            ? baseName
            : $"{this._blobNamePrefix}/{baseName}";
    }

    private static string ComputeKey(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value)));

    private static string? NormalizePrefix(string? prefix)
    {
        string? normalized = prefix?.Trim('/');
        return string.IsNullOrEmpty(normalized) ? null : normalized;
    }
}
