// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Mem0;

/// <summary>
/// Options for configuring the <see cref="Mem0Provider"/>.
/// </summary>
public sealed class Mem0ProviderOptions
{
    /// <summary>
    /// When providing memories to the model, this string is prefixed to the retrieved memories to supply context.
    /// </summary>
    /// <value>Defaults to "## Memories\nConsider the following memories when answering user questions:".</value>
    public string? ContextPrompt { get; set; }
}
