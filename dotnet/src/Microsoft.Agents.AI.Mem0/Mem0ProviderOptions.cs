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

    /// <summary>
    /// Gets or sets a value indicating whether sensitive data such as user ids and user messages may appear in logs.
    /// </summary>
    /// <value>Defaults to <see langword="false"/>.</value>
    public bool EnableSensitiveTelemetryData { get; set; }
}
