// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Agents.AI.Postgres;

/// <summary>
/// Represents one raw or derived memory stored by <see cref="PostgresMemoryClient"/>.
/// </summary>
public sealed class PostgresMemoryRecord
{
    /// <summary>
    /// Gets the database-generated record identifier.
    /// </summary>
    public long Id { get; init; }

    /// <summary>
    /// Gets the memory type.
    /// </summary>
    public PostgresMemoryType MemoryType { get; init; }

    /// <summary>
    /// Gets the stored memory content.
    /// </summary>
    public required string Content { get; init; }

    /// <summary>
    /// Gets the role associated with a raw turn, or <see langword="null"/> for derived memories.
    /// </summary>
    public string? Role { get; init; }

    /// <summary>
    /// Gets the stable user identifier.
    /// </summary>
    public required string UserId { get; init; }

    /// <summary>
    /// Gets the source thread identifier, when applicable.
    /// </summary>
    public string? ThreadId { get; init; }

    /// <summary>
    /// Gets the optional agent identifier.
    /// </summary>
    public string? AgentId { get; init; }

    /// <summary>
    /// Gets the optional application identifier.
    /// </summary>
    public string? ApplicationId { get; init; }

    /// <summary>
    /// Gets the extraction confidence for a derived memory.
    /// </summary>
    public double? Confidence { get; init; }

    /// <summary>
    /// Gets the optional importance score used to rank or filter memories.
    /// </summary>
    public double? Salience { get; init; }

    /// <summary>
    /// Gets the retrieval score when the record was returned by a search operation.
    /// </summary>
    public double? Score { get; init; }

    /// <summary>
    /// Gets the semantic relevance score returned by an optional second-stage reranker.
    /// </summary>
    public double? RerankerScore { get; init; }

    /// <summary>
    /// Gets the tags associated with the memory.
    /// </summary>
    public IReadOnlyList<string> Tags { get; init; } = [];

    /// <summary>
    /// Gets the record creation timestamp.
    /// </summary>
    public DateTimeOffset CreatedAt { get; init; }

    /// <summary>
    /// Gets the record update timestamp.
    /// </summary>
    public DateTimeOffset UpdatedAt { get; init; }

    /// <summary>
    /// Gets a value indicating whether this record was superseded by reconciliation.
    /// </summary>
    public bool IsSuperseded { get; init; }

    /// <summary>
    /// Gets the identifier of the record that superseded this record, when applicable.
    /// </summary>
    public long? SupersededBy { get; init; }

    /// <summary>
    /// Gets the reason this record was superseded, when applicable.
    /// </summary>
    public string? SupersedeReason { get; init; }

    internal PostgresMemoryRecord WithRerankerScore(double rerankerScore) =>
        new()
        {
            Id = this.Id,
            MemoryType = this.MemoryType,
            Content = this.Content,
            Role = this.Role,
            UserId = this.UserId,
            ThreadId = this.ThreadId,
            AgentId = this.AgentId,
            ApplicationId = this.ApplicationId,
            Confidence = this.Confidence,
            Salience = this.Salience,
            Score = this.Score,
            RerankerScore = rerankerScore,
            Tags = this.Tags,
            CreatedAt = this.CreatedAt,
            UpdatedAt = this.UpdatedAt,
            IsSuperseded = this.IsSuperseded,
            SupersededBy = this.SupersededBy,
            SupersedeReason = this.SupersedeReason,
        };
}
