// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure;
using Azure.Storage.Blobs;
using Azure.Storage.Blobs.Models;
using Microsoft.Shared.DiagnosticIds;
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
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AzureBlobAgentSessionStore : AgentSessionStore
{
    private const int MaxBlobNameLength = 1024;
    private const int BaseBlobNameLength = 137;

    private static readonly BlobUploadOptions s_uploadOptions = new()
    {
        HttpHeaders = new BlobHttpHeaders { ContentType = "application/json" },
    };
    private static readonly UTF8Encoding s_strictUtf8 = new(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true);

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
        this._agentKey = ComputeAgentKey(Throw.IfNullOrWhitespace(agentNamespace));

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
        AgentSessionStoreKey key,
        AgentSession session,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);
        Throw.IfNull(key);
        Throw.IfNull(session);

        await this.EnsureContainerExistsAsync(cancellationToken).ConfigureAwait(false);

        JsonElement serializedSession = await agent.SerializeSessionAsync(session, cancellationToken: cancellationToken).ConfigureAwait(false);
        BlobClient blobClient = this._containerClient.GetBlobClient(this.GetBlobName(key));
        await blobClient.UploadAsync(
            BinaryData.FromString(serializedSession.GetRawText()),
            s_uploadOptions,
            cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public override async ValueTask<AgentSession?> GetSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);
        Throw.IfNull(key);

        await this.EnsureContainerExistsAsync(cancellationToken).ConfigureAwait(false);

        return await this.TryGetSessionAsync(
            agent,
            this.GetBlobName(key),
            cancellationToken).ConfigureAwait(false);
    }

    private async ValueTask<AgentSession?> TryGetSessionAsync(
        AIAgent agent,
        string blobName,
        CancellationToken cancellationToken)
    {
        BlobClient blobClient = this._containerClient.GetBlobClient(blobName);
        try
        {
            Response<BlobDownloadResult> response = await blobClient.DownloadContentAsync(cancellationToken).ConfigureAwait(false);
            using JsonDocument document = JsonDocument.Parse(response.Value.Content);
            return await agent.DeserializeSessionAsync(document.RootElement, cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        catch (RequestFailedException ex) when (ex.ErrorCode == BlobErrorCode.BlobNotFound.ToString())
        {
            return null;
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
            await WaitWithCancellationAsync(initializationTask, cancellationToken).ConfigureAwait(false);
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

    private string GetBlobName(AgentSessionStoreKey key)
    {
        string baseName = $"v2/{this._agentKey}/{ComputeSessionKey(key)}.json";

        return this._blobNamePrefix is null
            ? baseName
            : $"{this._blobNamePrefix}/{baseName}";
    }

    private static string ComputeSessionKey(AgentSessionStoreKey key)
    {
        StringBuilder builder = new();
        AppendComponent(builder, 's', key.SessionId);
        foreach (KeyValuePair<string, string> partition in key.Partitions)
        {
            AppendComponent(builder, 'n', partition.Key);
            AppendComponent(builder, 'v', partition.Value);
        }

        return ComputeKey(builder.ToString());
    }

    private static void AppendComponent(StringBuilder builder, char prefix, string value)
        => builder.Append(prefix).Append(value.Length).Append(':').Append(value).Append('|');

    private static async Task WaitWithCancellationAsync(Task task, CancellationToken cancellationToken)
    {
        if (task.IsCompleted || !cancellationToken.CanBeCanceled)
        {
            await task.ConfigureAwait(false);
            return;
        }

        var cancellationTaskSource = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        using (cancellationToken.Register(() => cancellationTaskSource.TrySetCanceled()))
        {
            Task completedTask = await Task.WhenAny(task, cancellationTaskSource.Task).ConfigureAwait(false);
            await completedTask.ConfigureAwait(false);
        }
    }

    private static string ComputeKey(string value)
    {
        byte[] input = s_strictUtf8.GetBytes(value);
#if NET8_0_OR_GREATER
        return Convert.ToHexString(SHA256.HashData(input));
#else
        using SHA256 sha256 = SHA256.Create();
        byte[] hash = sha256.ComputeHash(input);
        char[] result = new char[hash.Length * 2];

        for (int index = 0; index < hash.Length; index++)
        {
            byte valueByte = hash[index];
            result[index * 2] = ToHexChar(valueByte >> 4);
            result[(index * 2) + 1] = ToHexChar(valueByte & 0x0F);
        }

        return new string(result);
#endif
    }

    private static string ComputeAgentKey(string agentNamespace)
    {
        try
        {
            return ComputeKey(agentNamespace);
        }
        catch (EncoderFallbackException exception)
        {
            throw new ArgumentException(
                "The agent namespace must contain valid UTF-16 text.",
                nameof(agentNamespace),
                exception);
        }
    }

#if !NET8_0_OR_GREATER
    private static char ToHexChar(int value)
        => (char)(value < 10 ? '0' + value : 'A' + value - 10);
#endif

    private static string? NormalizePrefix(string? prefix)
    {
        string? normalized = prefix?.Trim('/');
        return string.IsNullOrEmpty(normalized) ? null : normalized;
    }
}
