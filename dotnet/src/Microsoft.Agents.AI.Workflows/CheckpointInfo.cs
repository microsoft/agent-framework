// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Serialization;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents a checkpoint with a unique identifier.
/// </summary>
public sealed class CheckpointInfo : IEquatable<CheckpointInfo>
{
    /// <summary>
    /// Gets the unique identifier for the current session.
    /// </summary>
    public string SessionId { get; }

    /// <summary>
    /// The unique identifier for the checkpoint.
    /// </summary>
    public string CheckpointId { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="CheckpointInfo"/> class with a unique identifier.
    /// </summary>
    internal CheckpointInfo(string sessionId) : this(sessionId, Guid.NewGuid().ToString("N")) { }

    /// <summary>
    /// Initializes a new instance of the CheckpointInfo class with the specified session and checkpoint identifiers.
    /// </summary>
    /// <param name="sessionId">The unique identifier for the session. Cannot be null or empty.</param>
    /// <param name="checkpointId">The unique identifier for the checkpoint. Cannot be null or empty.</param>
    [JsonConstructor]
    public CheckpointInfo(string sessionId, string checkpointId)
    {
        this.SessionId = Throw.IfNullOrEmpty(sessionId);
        this.CheckpointId = Throw.IfNullOrEmpty(checkpointId);
    }

    /// <inheritdoc/>
    public bool Equals(CheckpointInfo? other) =>
        other is not null &&
        this.SessionId == other.SessionId &&
        this.CheckpointId == other.CheckpointId;

    /// <inheritdoc/>
    public override bool Equals(object? obj) => this.Equals(obj as CheckpointInfo);

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(this.SessionId, this.CheckpointId);

    /// <inheritdoc/>
    public override string ToString() => $"CheckpointInfo(SessionId: {this.SessionId}, CheckpointId: {this.CheckpointId})";
}
