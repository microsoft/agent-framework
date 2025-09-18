// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Serialization;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents a checkpoint with a unique identifier and a timestamp indicating when it was created.
/// </summary>
public sealed class CheckpointInfo : IEquatable<CheckpointInfo>
{
    /// <summary>
    /// Gets the unique identifier for the current run.
    /// </summary>
    public string RunId { get; }

    /// <summary>
    /// The unique identifier for the checkpoint.
    /// </summary>
    public string CheckpointId { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="CheckpointInfo"/> class with a unique identifier and the current
    /// UTC timestamp.
    /// </summary>
    /// <remarks>This constructor generates a new unique identifier using a GUID in a 32-character, lowercase,
    /// hexadecimal format  and sets the timestamp to the current UTC time.</remarks>
    internal CheckpointInfo(string runId) : this(runId, Guid.NewGuid().ToString("N")) { }

    [JsonConstructor]
    internal CheckpointInfo(string runId, string checkpointId)
    {
        this.RunId = Throw.IfNullOrEmpty(runId);
        this.CheckpointId = Throw.IfNullOrEmpty(checkpointId);
    }

    /// <inheritdoc/>
    public bool Equals(CheckpointInfo? other) =>
        other is not null &&
        this.RunId == other.RunId &&
        this.CheckpointId == other.CheckpointId;

    /// <inheritdoc/>
    public override bool Equals(object? obj) => this.Equals(obj as CheckpointInfo);

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(this.RunId, this.CheckpointId);

    /// <inheritdoc/>
    public override string ToString() => $"CheckpointInfo(RunId: {this.RunId}, CheckpointId: {this.CheckpointId})";
}
