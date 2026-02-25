// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.FoundryMemory;

/// <summary>
/// Allows scoping of memories for the <see cref="FoundryMemoryProvider"/>.
/// </summary>
/// <remarks>
/// Azure AI Foundry memories are scoped by a single string identifier that you control.
/// Common patterns include using a user ID, team ID, or other unique identifier
/// to partition memories across different contexts.
/// </remarks>
public sealed class FoundryMemoryProviderScope
{
    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryMemoryProviderScope"/> class with the specified scope identifier.
    /// </summary>
    /// <param name="scope">The scope identifier used to partition memories. Must not be null or whitespace.</param>
    /// <exception cref="ArgumentException">Thrown when <paramref name="scope"/> is null or whitespace.</exception>
    public FoundryMemoryProviderScope(string scope)
    {
        Throw.IfNullOrWhitespace(scope);
        this.Scope = scope;
    }

    /// <summary>
    /// Gets the scope identifier used to partition memories.
    /// </summary>
    /// <remarks>
    /// This value controls how memory is partitioned in the memory store.
    /// Each unique scope maintains its own isolated collection of memory items.
    /// For example, use a user ID to ensure each user has their own individual memory.
    /// </remarks>
    public string Scope { get; }
}
