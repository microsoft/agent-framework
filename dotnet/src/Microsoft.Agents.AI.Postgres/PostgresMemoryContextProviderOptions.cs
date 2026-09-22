// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Postgres;

/// <summary>
/// Configures how <see cref="PostgresMemoryContextProvider"/> retrieves and injects memory.
/// </summary>
public sealed class PostgresMemoryContextProviderOptions
{
    /// <summary>
    /// Gets or sets the number of memories retrieved for each agent invocation.
    /// </summary>
    public int TopK { get; set; } = 5;

    /// <summary>
    /// Gets or sets the minimum extraction confidence accepted during retrieval.
    /// </summary>
    public double MinConfidence { get; set; } = 0.7;

    /// <summary>
    /// Gets or sets the derived memory types included in retrieval.
    /// </summary>
    public IReadOnlyList<PostgresMemoryType> MemoryTypes { get; set; } =
        [PostgresMemoryType.Fact, PostgresMemoryType.Procedural];

    /// <summary>
    /// Gets or sets the text prepended to retrieved memories.
    /// </summary>
    public string ContextPrompt { get; set; } = "## Relevant Memories\nConsider these memories when responding:";

    /// <summary>
    /// Gets or sets the key used to persist provider state in an <see cref="AgentSession"/>.
    /// </summary>
    public string? StateKey { get; set; }

    /// <summary>
    /// Gets or sets an optional filter applied to request messages used to build the memory search query.
    /// </summary>
    /// <value>
    /// When <see langword="null"/>, only messages from external callers are included.
    /// </value>
    public Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? SearchInputMessageFilter { get; set; }

    /// <summary>
    /// Gets or sets an optional filter applied to request messages stored as turns.
    /// </summary>
    /// <value>
    /// When <see langword="null"/>, only messages from external callers are included.
    /// </value>
    public Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? StorageInputRequestMessageFilter { get; set; }

    /// <summary>
    /// Gets or sets an optional filter applied to response messages stored as turns.
    /// </summary>
    /// <value>
    /// When <see langword="null"/>, all response messages are included.
    /// </value>
    public Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? StorageInputResponseMessageFilter { get; set; }
}
