// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.FoundryMemory;

/// <summary>
/// Options for configuring the <see cref="FoundryMemoryProvider"/>.
/// </summary>
public sealed class FoundryMemoryProviderOptions
{
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

    /// <summary>
    /// Gets or sets the key used to store the provider state in the session's <see cref="AgentSessionStateBag"/>.
    /// </summary>
    /// <value>Defaults to the provider's type name.</value>
    public string? StateKey { get; set; }

    /// <summary>
    /// Gets or sets an optional filter function applied to request messages when building the search text to use when
    /// searching for relevant memories during <see cref="AIContextProvider.InvokingAsync"/>.
    /// </summary>
    /// <value>
    /// When <see langword="null"/>, the provider defaults to including only
    /// <see cref="AgentRequestMessageSourceType.External"/> messages.
    /// </value>
    public Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? SearchInputMessageFilter { get; set; }

    /// <summary>
    /// Gets or sets an optional filter function applied to request messages when determining which messages to
    /// extract memories from during <see cref="AIContextProvider.InvokedAsync"/>.
    /// </summary>
    /// <value>
    /// When <see langword="null"/>, the provider defaults to including only
    /// <see cref="AgentRequestMessageSourceType.External"/> messages.
    /// </value>
    public Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? StorageInputMessageFilter { get; set; }
}
