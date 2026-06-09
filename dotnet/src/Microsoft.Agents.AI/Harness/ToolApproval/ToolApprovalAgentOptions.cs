// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Options for configuring the <see cref="ToolApprovalAgent"/> middleware.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public class ToolApprovalAgentOptions
{
    /// <summary>
    /// Gets or sets the <see cref="System.Text.Json.JsonSerializerOptions"/> used for serializing argument values
    /// when storing rules and for persisting state.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, <see cref="AgentJsonUtilities.DefaultOptions"/> is used.
    /// </remarks>
    public JsonSerializerOptions? JsonSerializerOptions { get; set; }

    /// <summary>
    /// Gets or sets a collection of heuristic functions that can automatically approve function calls
    /// that would otherwise require user approval.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Each function receives a <see cref="FunctionCallContent"/> representing the tool call that requires approval
    /// and returns a <see cref="ValueTask{Boolean}"/> that resolves to <see langword="true"/> to auto-approve
    /// the call, or <see langword="false"/> to continue evaluating the next rule.
    /// </para>
    /// <para>
    /// Auto-approval rules are evaluated after standing rules (derived from prior user approvals) but before
    /// prompting the user. Rules are evaluated in order; the first rule returning <see langword="true"/>
    /// causes the function call to be auto-approved.
    /// </para>
    /// </remarks>
    public IEnumerable<Func<FunctionCallContent, ValueTask<bool>>>? AutoApprovalRules { get; set; }
}
