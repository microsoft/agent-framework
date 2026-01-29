// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.FoundryMemory;

/// <summary>
/// Options for configuring the <see cref="FoundryMemoryProvider"/>.
/// </summary>
public sealed class FoundryMemoryProviderOptions
{
    /// <summary>
    /// Gets or sets the name of the pre-existing memory store in Azure AI Foundry.
    /// </summary>
    /// <remarks>
    /// The memory store must be created in your Azure AI Foundry project before using this provider.
    /// </remarks>
    public string? MemoryStoreName { get; set; }

    /// <summary>
    /// When providing memories to the model, this string is prefixed to the retrieved memories to supply context.
    /// </summary>
    /// <value>Defaults to "## Memories\nConsider the following memories when answering user questions:".</value>
    public string? ContextPrompt { get; set; }

    /// <summary>
    /// Gets or sets the maximum number of memories to retrieve during search.
    /// </summary>
    /// <value>Defaults to 5.</value>
    public int MaxMemories { get; set; } = 5;

    /// <summary>
    /// Gets or sets the delay in seconds before memory updates are processed.
    /// </summary>
    /// <remarks>
    /// Setting to 0 triggers updates immediately without waiting for inactivity.
    /// Higher values allow the service to batch multiple updates together.
    /// </remarks>
    /// <value>Defaults to 0 (immediate).</value>
    public int UpdateDelay { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether sensitive data such as user ids and user messages may appear in logs.
    /// </summary>
    /// <value>Defaults to <see langword="false"/>.</value>
    public bool EnableSensitiveTelemetryData { get; set; }
}
