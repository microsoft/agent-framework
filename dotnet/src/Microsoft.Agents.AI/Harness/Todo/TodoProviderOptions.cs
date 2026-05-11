// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Options controlling the behavior of <see cref="TodoProvider"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class TodoProviderOptions
{
    /// <summary>
    /// Gets or sets custom instructions provided to the agent for using the todo tools.
    /// </summary>
    /// <value>
    /// When <see langword="null"/> (the default), the provider uses built-in instructions
    /// that guide the agent on how to manage todos effectively.
    /// </value>
    public string? Instructions { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether to suppress injecting the todo list message
    /// into the conversation context.
    /// </summary>
    /// <value>
    /// When <see langword="false"/> (the default), a synthetic user message summarizing the current
    /// todo list is injected at each invocation. When <see langword="true"/>, no message is injected.
    /// </value>
    public bool SuppressTodoListMessage { get; set; }

    /// <summary>
    /// Gets or sets a custom function that builds the todo list message text.
    /// </summary>
    /// <value>
    /// When <see langword="null"/> (the default), the provider generates a standard formatted list
    /// of todo items. When set, this function receives the current list of todo items and should
    /// return a formatted string to inject as a user message.
    /// </value>
    public Func<IReadOnlyList<TodoItem>, string>? TodoListMessageBuilder { get; set; }
}
