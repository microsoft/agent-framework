// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// A class containing any context that should be provided to the AI model
/// as supplied by an <see cref="AIContextProvider"/>.
/// </summary>
/// <remarks>
/// Each <see cref="AIContextProvider"/> has the ability to provide its own context for each invocation.
/// The <see cref="AIContext"/> class contains the additional context supplied by the <see cref="AIContextProvider"/>.
/// This context will be combined with context supplied by other providers before being passed to the AI model.
/// </remarks>
public sealed class AIContext
{
    /// <summary>
    /// Gets or sets any instructions to pass to the AI model in addition to any other prompts
    /// that it may already have (in the case of an agent), or chat history that may
    /// already exist.
    /// </summary>
    /// <remarks>
    /// These instructions will be transient and only apply to the current invocation.
    /// </remarks>
    public string? Instructions { get; set; }

    /// <summary>
    /// Gets or sets a list of messages to add to the chat history.
    /// </summary>
    /// <remarks>
    /// These messages will permanently be added to the chat history.
    /// </remarks>
    public IList<ChatMessage>? Messages { get; set; }

    /// <summary>
    /// Gets or sets a list of functions/tools to make available to the AI model for the current invocation.
    /// </summary>
    /// <remarks>
    /// These functions/tools will be transient and only apply to the current invocation.
    /// </remarks>
    public IList<AITool>? Tools { get; set; }
}
