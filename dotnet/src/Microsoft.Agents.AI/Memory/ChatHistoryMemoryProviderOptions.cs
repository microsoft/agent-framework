// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Options controlling the behavior of <see cref="ChatHistoryMemoryProvider"/>.
/// </summary>
public sealed class ChatHistoryMemoryProviderOptions
{
    /// <summary>
    /// Gets or sets a value indicating when the search should be executed.
    /// </summary>
    /// <value><see cref="SearchBehavior.BeforeAIInvoke"/> by default.</value>
    public SearchBehavior SearchTime { get; set; } = SearchBehavior.BeforeAIInvoke;

    /// <summary>
    /// Gets or sets the name of the exposed search tool when operating in on-demand mode.
    /// </summary>
    /// <value>Defaults to "Search".</value>
    public string? FunctionToolName { get; set; }

    /// <summary>
    /// Gets or sets the description of the exposed search tool when operating in on-demand mode.
    /// </summary>
    /// <value>Defaults to "Allows searching through previous chat history to help answer the user question.".</value>
    public string? FunctionToolDescription { get; set; }

    /// <summary>
    /// Gets or sets the context prompt prefixed to results.
    /// </summary>
    public string? ContextPrompt { get; set; }

    /// <summary>
    /// Gets or sets the maximum number of results to retrieve from the chat history.
    /// </summary>
    /// <value>
    /// Defaults to 3 if not set.
    /// </value>
    public int? MaxResults { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether sensitive data such as user ids and user messages may appear in logs.
    /// </summary>
    /// <value>Defaults to <see langword="false"/>.</value>
    public bool EnableSensitiveTelemetryData { get; set; }

    /// <summary>
    /// Gets or sets the key used to store provider state in the <see cref="AgentSession.StateBag"/>.
    /// </summary>
    /// <value>
    /// Defaults to the provider's type name. Override this if you need multiple
    /// <see cref="ChatHistoryMemoryProvider"/> instances with separate state in the same session.
    /// </value>
    public string? StateKey { get; set; }

    /// <summary>
    /// Gets or sets an optional filter function applied to request messages when constructing the search text to use
    /// to search for relevant chat history during <see cref="AIContextProvider.InvokingAsync"/>.
    /// </summary>
    /// <value>
    /// When <see langword="null"/>, the provider defaults to including only
    /// <see cref="AgentRequestMessageSourceType.External"/> messages.
    /// </value>
    public Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? SearchInputMessageFilter { get; set; }

    /// <summary>
    /// Gets or sets an optional filter function applied to request messages when storing recent chat history
    /// during <see cref="AIContextProvider.InvokedAsync"/>.
    /// </summary>
    /// <value>
    /// When <see langword="null"/>, the provider defaults to including only
    /// <see cref="AgentRequestMessageSourceType.External"/> messages.
    /// </value>
    public Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? StorageInputMessageFilter { get; set; }

    /// <summary>
    /// Behavior choices for the provider.
    /// </summary>
    public enum SearchBehavior
    {
        /// <summary>
        /// Execute search prior to each invocation and inject results as a message.
        /// </summary>
        BeforeAIInvoke,

        /// <summary>
        /// Expose a function tool to perform search on-demand via function/tool calling.
        /// </summary>
        OnDemandFunctionCalling
    }
}
