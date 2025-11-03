// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure;
using Azure.Storage.Blobs;
using Azure.Storage.Blobs.Models;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.AzureStorage.Blob;

internal sealed class AzureBlobAgentThreadStore : AgentThreadStore
{
    private static readonly BlobOpenWriteOptions s_uploadJsonOptions = new()
    {
        HttpHeaders = new()
        {
            ContentType = "application/json"
        }
    };

    private readonly BlobContainerClient _containerClient;
    private readonly AzureBlobAgentThreadStoreOptions _options;
    private bool _containerInitialized;

    /// <summary>
    /// Initializes a new instance of the <see cref="AzureBlobAgentThreadStore"/> class using a <see cref="BlobContainerClient"/>.
    /// </summary>
    /// <param name="containerClient">The blob container client to use for storage operations.</param>
    /// <param name="options">Optional configuration options. If <see langword="null"/>, default options will be used.</param>
    /// <exception cref="ArgumentNullException"><paramref name="containerClient"/> is <see langword="null"/>.</exception>
    public AzureBlobAgentThreadStore(BlobContainerClient containerClient, AzureBlobAgentThreadStoreOptions? options = null)
    {
        this._containerClient = containerClient ?? throw new ArgumentNullException(nameof(containerClient));
        this._options = options ?? new AzureBlobAgentThreadStoreOptions();
    }

    /// <inheritdoc/>
    public override async ValueTask SaveThreadAsync(
        AIAgent agent,
        string conversationId,
        AgentThread thread,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);
        Throw.IfNull(conversationId);
        Throw.IfNull(thread);

        await this.EnsureContainerExistsAsync(cancellationToken).ConfigureAwait(false);

        var blobName = this.GetBlobName(agent.Id, conversationId);
        var blobClient = this._containerClient.GetBlobClient(blobName);

        JsonElement serializedThread = thread.Serialize();
#pragma warning disable CA2007 // Consider calling ConfigureAwait on the awaited task
        await using Stream stream = await blobClient.OpenWriteAsync(overwrite: true, s_uploadJsonOptions, cancellationToken).ConfigureAwait(false);
        await using Utf8JsonWriter writer = new(stream);
#pragma warning restore CA2007 // Consider calling ConfigureAwait on the awaited task

        serializedThread.WriteTo(writer);
        await writer.FlushAsync(cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override async ValueTask<AgentThread> GetThreadAsync(
        AIAgent agent,
        string conversationId,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);
        Throw.IfNull(conversationId);

        await this.EnsureContainerExistsAsync(cancellationToken).ConfigureAwait(false);

        var blobName = this.GetBlobName(agent.Id, conversationId);
        var blobClient = this._containerClient.GetBlobClient(blobName);

        try
        {
            var stream = await blobClient.OpenReadAsync(cancellationToken: cancellationToken).ConfigureAwait(false);
            var jsonDoc = await JsonDocument.ParseAsync(stream, cancellationToken: cancellationToken).ConfigureAwait(false);
            var serializedThread = jsonDoc.RootElement;

            return agent.DeserializeThread(serializedThread);
        }
        catch (RequestFailedException ex) when (ex.Status == 404)
        {
            // Blob doesn't exist, return a new thread
            return agent.GetNewThread();
        }
    }

    /// <summary>
    /// Ensures that the blob container exists, creating it if necessary.
    /// </summary>
    private async Task EnsureContainerExistsAsync(CancellationToken cancellationToken)
    {
        if (this._containerInitialized)
        {
            return;
        }

        if (!this._containerInitialized)
        {
            if (this._options.CreateContainerIfNotExists)
            {
                await this._containerClient.CreateIfNotExistsAsync(cancellationToken: cancellationToken).ConfigureAwait(false);
            }

            this._containerInitialized = true;
        }
    }

    /// <summary>
    /// Generates the blob name for a given agent and conversation.
    /// </summary>
    private string GetBlobName(string agentId, string conversationId)
    {
        string sanitizedAgentId = this.SanitizeBlobNameSegment(agentId);
        string sanitizedConversationId = this.SanitizeBlobNameSegment(conversationId);
        string baseName = $"{sanitizedAgentId}/{sanitizedConversationId}.json";

        return string.IsNullOrEmpty(this._options.BlobNamePrefix)
            ? baseName
            : $"{this._options.BlobNamePrefix.TrimEnd('/')}/{baseName}";
    }

    /// <summary>
    /// Sanitizes a string to be safe for use in blob names.
    /// </summary>
    private string SanitizeBlobNameSegment(string input)
    {
        if (string.IsNullOrWhiteSpace(input))
        {
            return "default";
        }

        // Replace invalid characters with underscore
        StringBuilder builder = new(input.Length);
        foreach (char c in input)
        {
            if (char.IsLetterOrDigit(c) || c == '-' || c == '_' || c == '.')
            {
                builder.Append(c);
            }
            else
            {
                builder.Append('_');
            }
        }

        return builder.ToString();
    }
}
