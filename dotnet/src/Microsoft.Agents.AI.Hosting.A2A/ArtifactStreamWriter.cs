// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Agents.AI.Hosting.A2A.Converters;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Writes a stream of <see cref="AgentResponseUpdate"/> instances to a <see cref="TaskUpdater"/> as A2A artifacts.
/// </summary>
/// <remarks>
/// Each contiguous run of updates sharing a message ID becomes a single artifact streamed through artifact updates.
/// The latest parts are buffered until another update or message boundary determines whether they are the last
/// artifact update; earlier updates are appended and the final update closes the artifact. Updates without a message
/// ID continue the current artifact, or start one with a generated ID. A message ID is used as the artifact ID when
/// available; if it reappears later, a new artifact ID prevents the earlier artifact from being replaced.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
internal sealed class ArtifactStreamWriter
{
    /// <summary>
    /// The updater used to send artifact events.
    /// </summary>
    private readonly TaskUpdater _updater;

    /// <summary>
    /// The artifact IDs already assigned by this writer, used to detect repeated message IDs.
    /// </summary>
    private readonly HashSet<string> _usedArtifactIds = [];

    /// <summary>
    /// The message whose updates belong to the current artifact.
    /// </summary>
    private string? _currentMessageId;

    /// <summary>
    /// The unique ID used to write the current artifact.
    /// </summary>
    private string? _currentArtifactId;

    /// <summary>
    /// The update awaiting emission, held back until it is known whether it ends the artifact.
    /// </summary>
    private List<Part>? _bufferedParts;

    /// <summary>
    /// Whether the next flushed parts should be appended to the current artifact.
    /// </summary>
    private bool _shouldAppend;

    /// <summary>
    /// Whether an artifact write failed.
    /// </summary>
    private bool _writeFailed;

    /// <summary>
    /// Initializes a new instance of the <see cref="ArtifactStreamWriter"/> class.
    /// </summary>
    /// <param name="updater">The updater the artifacts are written to.</param>
    public ArtifactStreamWriter(TaskUpdater updater)
    {
        this._updater = updater;
    }

    /// <summary>
    /// Processes an update, writing the previously buffered parts once their position in the artifact is known.
    /// </summary>
    /// <param name="update">The update to write.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    public async Task WriteAsync(AgentResponseUpdate update, CancellationToken cancellationToken)
    {
        try
        {
            // Start the first artifact, generating an ID when the update does not provide one.
            if (this._currentArtifactId is null)
            {
                this.StartArtifact(update.MessageId);
            }
            // A different message ID ends the current artifact and starts the next one.
            else if (this.IsNewMessage(update.MessageId))
            {
                await this.FlushBufferedPartsIfAnyAsync(lastChunk: true, cancellationToken).ConfigureAwait(false);
                this.StartArtifact(update.MessageId);
            }

            // Flush the previous parts as a non-final artifact update before buffering the next content-bearing update.
            if (update.ToParts() is { Count: > 0 } parts)
            {
                await this.FlushBufferedPartsIfAnyAsync(lastChunk: false, cancellationToken).ConfigureAwait(false);
                this._bufferedParts = parts;
            }
        }
        catch
        {
            this._writeFailed = true;
            throw;
        }
    }

    /// <summary>
    /// Completes the stream by writing the buffered parts as the final artifact update.
    /// </summary>
    /// <remarks>
    /// Completion is skipped after an artifact write fails to avoid retrying and potentially duplicating that update.
    /// </remarks>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    public async Task CompleteAsync(CancellationToken cancellationToken)
    {
        if (this._writeFailed)
        {
            return;
        }

        try
        {
            await this.FlushBufferedPartsIfAnyAsync(lastChunk: true, cancellationToken).ConfigureAwait(false);
        }
        catch
        {
            this._writeFailed = true;
            throw;
        }
    }

    /// <summary>
    /// Flushes buffered parts to the current artifact.
    /// </summary>
    /// <param name="lastChunk">Whether the buffered parts form the final artifact update.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    private async Task FlushBufferedPartsIfAnyAsync(bool lastChunk, CancellationToken cancellationToken)
    {
        if (this._bufferedParts is null)
        {
            return;
        }

        await this._updater.AddArtifactAsync(
            this._bufferedParts,
            artifactId: this._currentArtifactId,
            lastChunk: lastChunk,
            append: this._shouldAppend,
            cancellationToken: cancellationToken).ConfigureAwait(false);

        this._bufferedParts = null;
        this._shouldAppend = true;
    }

    /// <summary>
    /// Determines whether the update starts a new message.
    /// </summary>
    /// <param name="messageId">The message ID from the update.</param>
    /// <returns><see langword="true"/> when the non-empty message ID differs from the current message ID.</returns>
    private bool IsNewMessage(string? messageId)
    {
        return messageId is { Length: > 0 } && messageId != this._currentMessageId;
    }

    /// <summary>
    /// Starts a new artifact, generating an ID when the message ID is missing or already used.
    /// </summary>
    /// <param name="messageId">The message ID, or <see langword="null"/> when the update does not provide one.</param>
    private void StartArtifact(string? messageId)
    {
        // Use a generated ID to group updates when the message ID is missing.
        this._currentMessageId = messageId is { Length: > 0 }
            ? messageId
            : Guid.NewGuid().ToString("N");

        // Preserve the message ID when possible, but avoid replacing an earlier artifact when it reappears.
        if (this._usedArtifactIds.Add(this._currentMessageId))
        {
            this._currentArtifactId = this._currentMessageId;
        }
        else
        {
            this._currentArtifactId = Guid.NewGuid().ToString("N");
            this._usedArtifactIds.Add(this._currentArtifactId);
        }

        this._shouldAppend = false;
    }
}
