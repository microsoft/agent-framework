// Copyright (c) Microsoft. All rights reserved.

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
    /// Initializes a new instance of the <see cref="FoundryMemoryProviderScope"/> class.
    /// </summary>
    public FoundryMemoryProviderScope() { }

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryMemoryProviderScope"/> class by cloning an existing scope.
    /// </summary>
    /// <param name="sourceScope">The scope to clone.</param>
    public FoundryMemoryProviderScope(FoundryMemoryProviderScope sourceScope)
    {
        Throw.IfNull(sourceScope);
        this.Scope = sourceScope.Scope;
    }

    /// <summary>
    /// Gets or sets the scope identifier used to partition memories.
    /// </summary>
    /// <remarks>
    /// This value controls how memory is partitioned in the memory store.
    /// Each unique scope maintains its own isolated collection of memory items.
    /// For example, use a user ID to ensure each user has their own individual memory.
    /// </remarks>
    public string? Scope { get; set; }
}
