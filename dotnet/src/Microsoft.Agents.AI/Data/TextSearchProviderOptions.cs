// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Data;

/// <summary>
/// Options controlling the behavior of <see cref="TextSearchProvider"/>.
/// </summary>
public sealed class TextSearchProviderOptions
{
    /// <summary>
    /// Gets or sets a value indicating when the search should be executed.
    /// </summary>
    /// <value><see cref="TextSearchBehavior.BeforeAIInvoke"/> by default.</value>
    public TextSearchBehavior SearchTime { get; set; } = TextSearchBehavior.BeforeAIInvoke;

    /// <summary>
    /// Gets or sets the name of the exposed search tool when operating in on-demand mode.
    /// </summary>
    /// <value>Defaults to "Search".</value>
    public string? FunctionToolName { get; set; }

    /// <summary>
    /// Gets or sets the description of the exposed search tool when operating in on-demand mode.
    /// </summary>
    /// <value>Defaults to "Allows searching for additional information to help answer the user question.".</value>
    public string? FunctionToolDescription { get; set; }

    /// <summary>
    /// Gets or sets the context prompt prefixed to results.
    /// </summary>
    public string? ContextPrompt { get; set; }

    /// <summary>
    /// Gets or sets the instruction appended after results to request citations.
    /// </summary>
    public string? CitationsPrompt { get; set; }

    /// <summary>
    /// Optional delegate to fully customize formatting of the result list.
    /// </summary>
    /// <remarks>
    /// If provided, <see cref="ContextPrompt"/> and <see cref="CitationsPrompt"/> are ignored.
    /// </remarks>
    public Func<IList<TextSearchProvider.TextSearchResult>, string>? ContextFormatter { get; set; }

    /// <summary>
    /// Gets or sets the number of recent conversation messages (both user and assistant) to keep in memory
    /// and include when constructing the search input for <see cref="TextSearchBehavior.BeforeAIInvoke"/> searches.
    /// </summary>
    /// <value>
    /// The maximum number of most recent messages to retain. A value of <c>0</c> (default) disables memory and
    /// only the current request's messages are used for search input. The value is a count of individual
    /// messages, not turns. Only messages with role <see cref="ChatRole.User"/> or
    /// <see cref="ChatRole.Assistant"/> are retained.
    /// </value>
    public int RecentMessageMemoryLimit { get; set; }

    /// <summary>
    /// Gets or sets the list of <see cref="ChatRole"/> types to filter recent messages to
    /// when deciding which recent messages to include when constructing the search input.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Depending on your scenario, you may want to use only user messages, only assistant messages,
    /// or both. For example, if the assistant may often provide clarifying questions or if the conversation
    /// is expected to be particularly chatty, you may want to include assistant messages in the search context as well.
    /// </para>
    /// <para>
    /// Be careful when including assistant messages though, as they may skew the search results towards
    /// information that has already been provided by the assistant, rather than focusing on the user's current needs.
    /// </para>
    /// </remarks>
    /// <value>
    /// When not specified, defaults to only <see cref="ChatRole.User"/>.
    /// </value>
    public List<ChatRole>? RecentMessageRolesIncluded { get; set; }

    /// <summary>
    /// Behavior choices for the provider.
    /// </summary>
    public enum TextSearchBehavior
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
