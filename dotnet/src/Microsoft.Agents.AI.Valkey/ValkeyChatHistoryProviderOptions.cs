// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Valkey;

/// <summary>
/// Options for configuring <see cref="ValkeyChatHistoryProvider"/>.
/// </summary>
public sealed class ValkeyChatHistoryProviderOptions
{
    /// <summary>
    /// Gets or sets the prefix for Valkey keys. Defaults to "chat_history".
    /// </summary>
    public string KeyPrefix { get; set; } = "chat_history";

    /// <summary>
    /// Gets or sets the maximum number of messages to retain per conversation.
    /// When exceeded, oldest messages are automatically trimmed. Null means unlimited.
    /// </summary>
    public int? MaxMessages { get; set; }

    /// <summary>
    /// Gets or sets the maximum number of messages to retrieve from the provider.
    /// Null means no limit.
    /// </summary>
    public int? MaxMessagesToRetrieve { get; set; }

    /// <summary>
    /// Gets or sets an optional key for storing state in the session's StateBag.
    /// </summary>
    public string? StateKey { get; set; }

    /// <summary>
    /// Gets or sets optional JSON serializer options for serializing the state of this provider.
    /// </summary>
    public JsonSerializerOptions? JsonSerializerOptions { get; set; }

    /// <summary>
    /// Gets or sets an optional filter for messages when retrieving from history.
    /// </summary>
    public Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? ProvideOutputMessageFilter { get; set; }

    /// <summary>
    /// Gets or sets an optional filter for request messages before storing.
    /// </summary>
    public Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? StoreInputRequestMessageFilter { get; set; }

    /// <summary>
    /// Gets or sets an optional filter for response messages before storing.
    /// </summary>
    public Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? StoreInputResponseMessageFilter { get; set; }
}
