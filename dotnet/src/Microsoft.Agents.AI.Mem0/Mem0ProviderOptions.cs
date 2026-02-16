// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;

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
