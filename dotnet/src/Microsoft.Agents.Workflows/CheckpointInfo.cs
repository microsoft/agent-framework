// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents a checkpoint with a unique identifier and a timestamp indicating when it was created.
/// </summary>
public class CheckpointInfo : IEquatable<CheckpointInfo>
{
    /// <summary>
    /// The unique identifier for the checkpoint.
    /// </summary>
    public string CheckpointId { get; } = Guid.NewGuid().ToString("N");

    /// <summary>
    /// The date and time when the object was created, in Coordinated Universal Time (UTC).
    /// </summary>
    public DateTimeOffset CreatedAt { get; } = DateTimeOffset.UtcNow;

    /// <inheritdoc/>
    public bool Equals(CheckpointInfo? other)
    {
        if (other == null)
        {
            return false;
        }

        return this.CheckpointId == other.CheckpointId &&
               this.CreatedAt == other.CreatedAt;
    }

    /// <inheritdoc/>
    public override bool Equals(object? obj)
    {
        return this.Equals(obj as CheckpointInfo);
    }

    /// <inheritdoc/>
    public override int GetHashCode()
    {
        return HashCode.Combine(this.CheckpointId, this.CreatedAt);
    }

    /// <inheritdoc/>
    public override string ToString() => $"CheckpointId: {this.CheckpointId}, CreatedAt: {this.CreatedAt:O}";
}
