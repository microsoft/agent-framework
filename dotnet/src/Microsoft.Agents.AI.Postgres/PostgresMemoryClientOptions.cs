// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Postgres;

/// <summary>
/// Specifies the approximate nearest neighbor index used for memory embeddings.
/// </summary>
public enum PostgresMemoryVectorIndexKind
{
    /// <summary>
    /// Uses the pgvector Hierarchical Navigable Small Worlds index.
    /// </summary>
    Hnsw,

    /// <summary>
    /// Uses the pg_diskann DiskANN index available in Azure Database for PostgreSQL flexible server.
    /// </summary>
    DiskAnn,
}

/// <summary>
/// Configures storage, retrieval, and processing behavior for <see cref="PostgresMemoryClient"/>.
/// </summary>
public sealed class PostgresMemoryClientOptions
{
    /// <summary>
    /// Gets or sets the PostgreSQL schema that contains the memory tables.
    /// </summary>
    public string Schema { get; set; } = "public";

    /// <summary>
    /// Gets or sets the base table name used to derive <c>_turns</c>, <c>_memories</c>,
    /// <c>_summaries</c>, and <c>_processing</c> tables.
    /// </summary>
    public string TableName { get; set; } = "agent_memories";

    /// <summary>
    /// Gets or sets a value indicating whether the client creates its schema and tables on first use.
    /// </summary>
    public bool EnsureSchemaOnFirstUse { get; set; } = true;

    /// <summary>
    /// Gets or sets the embedding vector dimensions.
    /// </summary>
    public int EmbeddingDimensions { get; set; } = 1536;

    /// <summary>
    /// Gets or sets the approximate nearest neighbor index used for memory embeddings.
    /// </summary>
    public PostgresMemoryVectorIndexKind VectorIndexKind { get; set; } = PostgresMemoryVectorIndexKind.Hnsw;

    /// <summary>
    /// Gets or sets the Reciprocal Rank Fusion constant used by hybrid retrieval.
    /// </summary>
    public int ReciprocalRankFusionK { get; set; } = 60;

    /// <summary>
    /// Gets or sets a value indicating whether hybrid search candidates are reranked with
    /// <c>azure_ai.rank()</c> before results are returned.
    /// </summary>
    public bool EnableAzureAiReranking { get; set; }

    /// <summary>
    /// Gets or sets the Foundry model deployment used by <c>azure_ai.rank()</c>.
    /// </summary>
    public string AzureAiRerankerModel { get; set; } = "cohere-rerank-v3.5";

    /// <summary>
    /// Gets or sets the maximum number of hybrid search candidates sent to the reranker.
    /// </summary>
    public int RerankingCandidateCount { get; set; } = 25;

    /// <summary>
    /// Gets or sets a value indicating whether raw conversation turns are embedded.
    /// </summary>
    public bool EnableTurnEmbeddings { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether turn writes schedule cadence-aware background processing.
    /// </summary>
    public bool AutoProcess { get; set; } = true;

    /// <summary>
    /// Gets or sets the number of new turns between memory extraction runs. Zero disables automatic extraction.
    /// </summary>
    public int FactExtractionEveryNTurns { get; set; } = 2;

    /// <summary>
    /// Gets or sets the number of extraction runs between reconciliation passes. Zero disables automatic reconciliation.
    /// </summary>
    public int ReconcileEveryNExtractions { get; set; } = 5;

    /// <summary>
    /// Gets or sets the maximum number of recent memories considered by one reconciliation pass.
    /// </summary>
    public int ReconciliationPoolSize { get; set; } = 50;

    /// <summary>
    /// Gets or sets the number of new turns between thread-summary updates. Zero disables automatic thread summaries.
    /// </summary>
    public int ThreadSummaryEveryNTurns { get; set; } = 10;

    /// <summary>
    /// Gets or sets the number of new turns across the user scope between user-summary updates.
    /// Zero disables automatic user summaries.
    /// </summary>
    public int UserSummaryEveryNTurns { get; set; } = 20;

    /// <summary>
    /// Gets or sets the cosine-similarity threshold used to fold paraphrased duplicate memories.
    /// </summary>
    public double DedupeSimilarityThreshold { get; set; } = 0.92;

    /// <summary>
    /// Gets or sets the default lifetime of episodic memories. Set to <see langword="null"/> to retain them indefinitely.
    /// </summary>
    public TimeSpan? EpisodicMemoryTimeToLive { get; set; } = TimeSpan.FromDays(90);

    /// <summary>
    /// Gets or sets customizable prompts for the memory-processing pipeline.
    /// </summary>
    public PostgresMemoryPromptOptions Prompts { get; set; } = new();
}
