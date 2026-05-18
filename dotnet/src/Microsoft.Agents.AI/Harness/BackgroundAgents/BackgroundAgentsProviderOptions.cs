// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Options controlling the behavior of <see cref="BackgroundAgentsProvider"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class BackgroundAgentsProviderOptions
{
    /// <summary>
    /// Gets or sets custom instructions provided to the agent for using the background agent tools.
    /// </summary>
    /// <remarks>
    /// Use the <c>{background_agents}</c> placeholder to allow the provider to inject
    /// the formatted list of available background agents.
    /// </remarks>
    /// <value>
    /// When <see langword="null"/> (the default), the provider uses built-in instructions
    /// that guide the agent on how to use the background agent tools.
    /// The agent list is always appended after the instructions regardless of this setting.
    /// </value>
    public string? Instructions { get; set; }

    /// <summary>
    /// Gets or sets a custom function that builds the agent list text to append to instructions.
    /// </summary>
    /// <value>
    /// When <see langword="null"/> (the default), the provider generates a standard list of agent names and descriptions.
    /// When set, this function receives the dictionary of available agents (keyed by name) and should return
    /// a formatted string describing the available background agents.
    /// </value>
    public Func<IReadOnlyDictionary<string, AIAgent>, string>? AgentListBuilder { get; set; }
}
