// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents a standing approval rule for automatically approving tool calls
/// without requiring explicit user approval each time.
/// </summary>
/// <remarks>
/// <para>
/// A rule can match tool calls in two ways:
/// <list type="bullet">
/// <item><b>Tool-level</b>: When <see cref="Arguments"/> is <see langword="null"/>,
/// all calls to the tool identified by <see cref="ToolName"/> are auto-approved.</item>
/// <item><b>Tool+arguments</b>: When <see cref="Arguments"/> is non-null,
/// only calls to the specified tool with exactly matching argument values are auto-approved.</item>
/// </list>
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal sealed class ToolApprovalRule
{
    /// <summary>
    /// Gets or sets the name of the tool function that this rule applies to.
    /// </summary>
    [JsonPropertyName("toolName")]
    public string ToolName { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets the specific argument values that must match for this rule to apply.
    /// When <see langword="null"/>, the rule applies to all invocations of the tool
    /// regardless of arguments.
    /// </summary>
    /// <remarks>
    /// Argument values are stored as their JSON-serialized string representations
    /// for reliable comparison.
    /// </remarks>
    [JsonPropertyName("arguments")]
    public IDictionary<string, string>? Arguments { get; set; }
}
