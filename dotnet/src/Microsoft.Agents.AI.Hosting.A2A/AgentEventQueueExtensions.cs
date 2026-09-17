// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using A2A;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Provides extensions for writing A2A events to an <see cref="AgentEventQueue"/>.
/// </summary>
internal static class AgentEventQueueExtensions
{
    /// <summary>
    /// Adds an artifact with metadata until the minimum A2A package version provides this capability on
    /// <see cref="TaskUpdater.AddArtifactAsync"/>.
    /// </summary>
    /// <remarks>
    /// Remove this method and call <see cref="TaskUpdater.AddArtifactAsync"/> directly after upgrading to an A2A
    /// package version whose overload accepts artifact metadata.
    /// </remarks>
    public static ValueTask AddArtifactAsync(
        this AgentEventQueue eventQueue,
        TaskUpdater updater,
        IReadOnlyList<Part> parts,
        string? artifactId = null,
        string? name = null,
        string? description = null,
        bool lastChunk = true,
        bool append = false,
        Dictionary<string, JsonElement>? metadata = null,
        CancellationToken cancellationToken = default) =>
        eventQueue.EnqueueArtifactUpdateAsync(new TaskArtifactUpdateEvent
        {
            TaskId = updater.TaskId,
            ContextId = updater.ContextId,
            Artifact = new Artifact
            {
                ArtifactId = artifactId ?? Guid.NewGuid().ToString("N"),
                Name = name,
                Description = description,
                Parts = [.. parts],
                Metadata = metadata,
            },
            Append = append,
            LastChunk = lastChunk,
        }, cancellationToken);
}
